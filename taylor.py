import os
import json
import signal
import logging
from copy import deepcopy

import pykka
import pykka.debug
from GameBlock import Message, Question, State
from FileReader import FileReader
from main import parse

logging.basicConfig(level=logging.DEBUG)
signal.signal(signal.SIGUSR1, pykka.debug.log_thread_tracebacks)


SAVES_DIR = 'saves'


class Game(object):
    def __init__(self, story_filename='StoryData_de.txt'):
        self.blocks = parse(FileReader(story_filename))

    def block(self, label):
        return deepcopy(self.blocks[label])


lifeline = Game()


def load(comline, savefile):
    with open(savefile) as f:
        data = json.load(f)
    return data['chat_id'], Taylor.start(
        data['chat_id'], comline,
        State(data['block_label'], data['parameters']), data['skip'])


def save(chat_id, state, skip=0):
    if not os.path.exists(SAVES_DIR):
        os.mkdir(SAVES_DIR)

    filename = os.path.join(SAVES_DIR, '{0}.json'.format(chat_id))
    with open(filename, 'w') as f:
        json.dump({
            'chat_id': chat_id,
            'block_label': state.block_label,
            'parameters': state.parameters,
            'skip': skip
        }, f)


class Taylor(pykka.ThreadingActor):
    def __init__(self, chat_id, comline, state=None, skip=0):
        super(Taylor, self).__init__()
        # const
        self.chat_id = chat_id
        self.comline = comline
        # game state
        self.state = state or State('Start', {})
        self.skip = skip

    def _start_communication(self):
        return Communication.start(
            self.actor_ref, self.chat_id, self.comline,
            self.state, self.skip)

    def on_start(self):
        self._communication = self._start_communication()

    def restart(self):
        self.state = State('Start', {})
        self.parameters = {}
        self.skip = 0
        self.actor_ref.proxy().on_start()

    def answer(self, ans):
        try:
            self._communication.proxy().answer(ans)
        except pykka.ActorDeadError:
            logging.error('{}: Answer without communication.'.format(
                self.chat_id))

    def end_communication(self, new_state):
        if new_state.block_label is None:  # game over
            self.stop()
            return

        self.state = new_state
        self.skip = 0
        save(self.chat_id, self.state)

        self._communication = self._start_communication()


class Communication(pykka.ThreadingActor):
    def __init__(self, taylor, chat_id, comline, state, skip=0):
        super(Communication, self).__init__()
        # serializable state
        self.taylor_proxy = taylor.proxy()
        self.chat_id = chat_id
        self.comline = comline
        self.state = state
        self.step = 0

        self.execution = lifeline.block(
            state.block_label).execute(state.parameters)
        self.skip = skip

    def on_start(self):
        self.next()

    def next(self):
        while self.skip > 0:
            result = next(self.execution)
            if isinstance(result, Question):
                logging.warning(
                    "{}: Cannot skip further due to question.".format(
                        self.chat_id))
                break
            self.skip -= 1
            self.step += 1
        else:
            result = next(self.execution)

        logging.debug('{}: --> {}'.format(self.chat_id, result))
        logging.debug(type(result))

        if isinstance(result, Message):
            self.message(result)
            save(self.chat_id, self.state, self.step)
        elif isinstance(result, Question):
            self.question(result)
        elif isinstance(result, State):
            self.new_state(result)
        else:
            assert(False)  # should never arrive here

        self.step += 1

    def _tell(self, text, **extra):
        message = {
            'from': 'taylor',
            'chat_id': self.chat_id,
            'text': text
        }
        message.update(**extra)
        self.comline.tell(message)

    def message(self, msg):
        logging.debug('{0}: Message {1}'.format(self.chat_id, msg.message))
        self._tell(msg.message)
        self.actor_ref.proxy().next()

    def question(self, q):
        logging.debug('{0}: Questions {1}'.format(self.chat_id, q.answers))
        self._question = q
        self._tell(q.question, answers=q.answers)

    def answer(self, ans):
        if self._question is None:
            logging.error(
                '{}: I am not awaiting any answers.'.format(self.chat_id))
            return

        if ans not in self._question.answers:
            logging.error(
                '{0}: Unexpected answer {1}'.format(self.chat_id, ans))
            return

        self._question.answer = self._question.answers.index(ans)
        self._question = None
        self.actor_ref.proxy().next()

    def new_state(self, state):
        try:
            self.taylor_proxy.end_communication(state)
        except pykka.ActorDeadError:
            logging.error(
                "{}: Sent a message to a dead Taylor!".format(self.chat_id))
        self.stop()
