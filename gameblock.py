import re
import time


DELAY_TABLE = {
    'none': 0,
    'zero': 0,
    'short': 1.5,
    'norm': 2.5,
    'normal': 2.5,
    'long': 3.5,
    'long long': 5
}


class Message(object):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return 'Message({})'.format(self.message)


class Question(object):
    def __init__(self, question, answers):
        self.question = question or 'Auswahl: '
        self.answers = answers
        self.answer = None

    def __repr__(self):
        return 'Question({}, {})'.format(self.question, self.answers)


class State(object):
    def __init__(self, block_label, parameters):
        self.block_label = block_label
        self.parameters = parameters

    def __repr__(self):
        return 'State({}, params=...)'.format(self.block_label)


class GameBlock:
    def __init__(self, name):
        self.name = name
        self.scripts = []
        self.nextName = None
        self.__jumpNow = False
        self.__if = [True]
        self.__silently = False
        self.__choicesJump = []
        self.__choicesShow = []
        self.__choices = 0
        self.__message = None

    def __doChoice(self, script):
        tagStart = script.find('[[')
        tagPipe = script.find('|')
        tagEnd = script.find(']]')
        key = script[tagPipe + 1:tagEnd].strip()
        value = script[tagStart + 2:tagPipe].strip()
        self.__choicesJump.append(key)
        self.__choicesShow.append(value)
        self.__choices += 1

    def __doIf(self, script):
        parameter = self.__parameter  # is used in eval below!
        script = script.replace('<<if', '')
        script = script.replace('<<elseif', '')
        script = script.replace('>>', '')
        script = script.replace(' is ', ' == ')
        script = script.replace(' eq ', ' == ')
        script = script.replace(' gte ', ' >= ')
        script = re.sub(
            r'\$(\S+)', r'parameter["\1"]', script)
        script = script.strip()
        self.__if[-1] = eval(script)

    def __doElse(self, script):
        self.__if[-1] = not self.__if[-1]

    def __doEndIf(self, script):
        self.__if.pop()

    def __doJudge(self, script):
        if script.startswith('<<if'):
            self.__if.append(True)
            self.__doIf(script)
            return
        if script.startswith('<<elseif'):
            self.__doIf(script)
            return
        if script.startswith('<<endif'):
            self.__doEndIf(script)
            return
        if script.startswith('<<else'):
            self.__doElse(script)
            return

    def __doJump(self, script):
        if script.startswith('[[delay'):
            pipPosition = script.find('|')
            self.nextName = script[pipPosition + 1:-2]
            yield from self.__delay(time_delay='long', busy=True)
        else:
            self.nextName = script[2:-2]
        self.__jumpNow = True

    def __doSet(self, script):
        parameter = self.__parameter
        script = script.replace('<<set ', '')
        script = script.replace('>>', '')
        script = re.sub(r'\$(\S+)', r'parameter["\1"]', script)
        script = script.strip()
        exec(script)
        self.__parameter = parameter

    def __doSilently(self, script):
        self.__silently = script.startswith('<<silently')

    def __doPrintParameter(self, script):
        tagStart = script.find('$')
        tagEnd = script.find('>>')
        parameter = script[tagStart + 1:tagEnd]
        try:
            yield str(self.__parameter[parameter])
        except:
            pass

    def __doScript(self, script):
        if script.startswith('<<if') or script.startswith('<<elseif') or \
                script.startswith('<<endif') or script.startswith('<<else'):
            self.__doJudge(script)
            return
        if self.__if[-1]:
            if script.startswith('[['):
                yield from self.__doJump(script)
                return
            if script.startswith('<<silently'):
                self.__doSilently(script)
                return
            if script.startswith('<<choice'):
                self.__doChoice(script)
                return
            if script.startswith('<<set'):
                self.__doSet(script)
                return
            if script.startswith('<<$'):
                yield from self.__doPrintParameter(script)
                return

    def __makeChoice(self, message):
        yield from self.__delay()
        q = Question(message, self.__choicesShow)
        yield(q)
        assert(q.answer is not None)
        self.nextName = self.__choicesJump[q.answer]

    def __delay(self, time_delay='short', busy=False):
        delay = 1.5
        if isinstance(time_delay, int):
            delay = time_delay
        elif isinstance(time_delay, str):
            if time_delay not in DELAY_TABLE.keys():
                time_delay = 'norm'
            delay = DELAY_TABLE[time_delay]
        if busy:
            yield(Message('[Taylor ist beschaeftigt...]'))
        time.sleep(delay)

    def execute(self, parameter):
        self.__parameter = parameter
        for script in self.scripts:
            if script.startswith('<<') or script.startswith('[['):
                yield from self.__doScript(script)
                if self.__choices == 2:
                    yield from self.__makeChoice(self.__message)
                    break
                continue
            if self.__if[-1]:
                if self.__message:
                    yield from self.__delay()
                    yield(Message(self.__message))
                self.__message = script

            if self.__jumpNow:
                break
        yield(State(self.nextName, self.__parameter))


def parse(reader):
    """ Parse game blocks from FileReader. """
    blocks = {}
    blockName = None
    blocks[blockName] = GameBlock(blockName)
    for line in reader:
        if 0 == len(line):
            continue
        if line.startswith('//'):
            continue
        if line.startswith(':: '):
            blockName = line[3:].strip()
            if blockName not in blocks.keys():
                blocks[blockName] = GameBlock(blockName)
            continue
        blocks[blockName].scripts.append(line)
    return blocks
