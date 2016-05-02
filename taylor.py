import os
import json
import signal
import logging
from copy import copy

import pykka
import pykka.debug
from GameBlock import Message, Question, State
from FileReader import FileReader
from main import parse

logging.basicConfig(level=logging.DEBUG)
signal.signal(signal.SIGUSR1, pykka.debug.log_thread_tracebacks)


SAVES_DIR = 'saves'


class Game(object):
    def __init__(self, story_filename='../story.txt'):
        self.blocks = parse(FileReader(story_filename))

    def block(self, label):
        return copy(self.blocks[label])


lifeline = Game()


def load(chat_id):
    filename = os.path.join(SAVES_DIR, '{0}.json'.format(chat_id))
    with open(filename) as f:
        data = json.load(f)
    return Taylor.start(**data)


def save(chat_id, block_label, game_state, skip=0):
    filename = os.path.join(SAVES_DIR, '{0}.json'.format(chat_id))
    with open(filename, 'w') as f:
        json.dump({
            'chat_id': chat_id,
            'block_label': block_label,
            'game_state': game_state,
            'skip': skip
        }, f)


class Taylor(pykka.ThreadingActor):
    def __init__(self, chat_id, block_label='launch', game_state=None, skip=0):
        super(Taylor, self).__init__()
        self.chat_id = chat_id
        self.block_label = block_label
        self.game_state = game_state or {}
        self.skip = skip

    def _open_comline(self):
        return Comline.start(
            self.actor_ref, self.chat_id, self.block_label, self.game_state,
            self.skip)

    def restart(self):
        self.block_label = 'launch'
        self.game_state = {}
        self.skip = 0
        self.actor_ref.proxy().on_start()

    def on_start(self):
        self._open_comline()

    def end_comline(self, new_block_label, new_game_state):
        if new_block_label is None:  # game over
            self.stop()
            return

        self.block_label = new_block_label
        self.game_state = new_game_state
        self.skip = 0
        save(self.chat_id, self.block_label, self.game_state)

        self._open_comline()


class Comline(pykka.ThreadingActor):
    def __init__(self, taylor, chat_id, block_label, game_state, skip=0):
        super(Comline, self).__init__()
        # serializable state
        self.taylor_proxy = taylor.proxy()
        self.chat_id = chat_id
        self.block_label = block_label
        self.game_state = game_state
        self.step = 0

        self.execution = lifeline.block(block_label).execute(game_state)
        self.skip = skip

    def on_start(self):
        self.next()

    def next(self):
        while self.skip > 0:
            result = next(self.execution)
            if isinstance(result, Question):
                logging.warning("Cannot further skip due to question.")
                print(self.step)
                break
            self.skip -= 1
            self.step += 1
        else:
            result = next(self.execution)

        if isinstance(result, Message):
            self.message(result)
            save(self.chat_id, self.block_label, self.game_state, self.step)
        elif isinstance(result, Question):
            self.question(result)
        elif isinstance(result, State):
            self.new_state(result)
        else:
            assert(False)  # should never arrive here

        self.step += 1

    def message(self, msg):
        print(msg.message)
        self.actor_ref.proxy().next()

    def question(self, question):
        print()
        for num, q in zip(
                range(1, len(question.questions) + 1), question.questions):
            print("[{}]: {}".format(num, q))
        num = -1
        while not (1 <= num and num <= len(question.questions)):
            try:
                num = int(input('Your Answer: '))
            except:
                num = -1
        question.answer = num - 1
        self.actor_ref.proxy().next()

    def new_state(self, result):
        self.taylor_proxy.end_comline(result.block_label, result.parameters)
        self.stop()


def main():
    if not os.path.exists(SAVES_DIR):
        os.mkdir(SAVES_DIR)

    if os.path.exists(SAVES_DIR + "/42.json"):
        load(42)
    else:
        Taylor.start(42)

if __name__ == '__main__':
    main()
