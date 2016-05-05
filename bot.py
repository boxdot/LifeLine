import os
import json
import glob
import logging
import pykka
import requests
from flask import Flask, request
from taylor import Taylor, State, SAVES_DIR, load

TOKEN = 'YOUR TELEGRAM BOT KEY HERE'


class Telegram(pykka.ThreadingActor):
    def __init__(self, token):
        super(Telegram, self).__init__()
        self.token = token
        self.games = {}

    def on_start(self):
        for savefile in glob.glob(os.path.join(SAVES_DIR, '*.json')):
            chat_id, taylor = load(self.actor_ref, savefile)
            self.games[chat_id] = taylor

    def on_receive(self, msg):
        if msg.get('from') == 'taylor':
            self.handle_taylors_msg(msg)
            return

        chat_id = msg.get('chat').get('id')
        incom = msg.get('text')
        logging.debug("Incoming from {0}: {1}".format(chat_id, incom))

        if incom == '/start':
            if chat_id in self.games and self.games[chat_id].is_alive():
                self.actor_ref.proxy().send_message(
                    chat_id, "Check. Check. Ich bin immer noch da.")
                return
            self.games[chat_id] = Taylor.start(chat_id, self.actor_ref)
        if incom.startswith('/jumpto'):
            block_label = incom.split(' ', 1)[1]
            if chat_id in self.games:
                try:
                    self.games[chat_id].stop()
                except pykka.ActorDeadError:
                    pass
            self.games[chat_id] = Taylor.start(
                chat_id, self.actor_ref, State(block_label, {}))
        elif chat_id in self.games:
            self.games[chat_id].proxy().answer(incom)

    def handle_taylors_msg(self, msg):
        if 'answers' in msg:
            answers = [[ans] for ans in msg['answers']]
            self.send_message(
                msg['chat_id'], text=msg['text'], keyboard=answers)
        else:
            self.send_message(msg['chat_id'], text=msg['text'], keyboard=False)

    def send_message(self, chat_id, text=None, keyboard=None):
        message = {
            'chat_id': chat_id,
            'text': text or '...'
        }
        if keyboard is False:
            message['reply_markup'] = json.dumps({
                'hide_keyboard': True
            })
        elif keyboard is not None:
            message['reply_markup'] = json.dumps({
                'keyboard': keyboard,
                'resize_keyboard': True,
                'one_time_keyboard': True
            })

        logging.debug('Sending to telegram {}'.format(message))
        requests.post('https://api.telegram.org/bot{0}/sendMessage'.format(
            self.token), data=message)


app = Flask(__name__)
telegram = Telegram.start(TOKEN)


@app.route('/')
def index():
    return 'Hello from Taylor Bot!'


@app.route('/', methods=['POST'])
def telegram_webhook():
    if request.json is None:
        app.logger.info("Got unexpected message. Drop it.")
        return 'ok'

    msg = request.json.get('message', None)
    if msg and msg.get('text'):
        telegram.tell(msg)
    return 'ok'


def main():
    app.run(host='localhost', port=61080, threaded=False, debug=False)


if __name__ == '__main__':
    main()
