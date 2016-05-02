import sys

from FileReader import FileReader
from GameBlock import GameBlock, Message, Question, State


def parse(reader):
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


def main():
    reader = FileReader('../story.txt')
    blocks = parse(reader)
    state = {}

    label = 'launch'
    while label in blocks:
        steps = iter(blocks[label].execute(state))
        for step in steps:
            if isinstance(step, Message):
                print(step.message)
            elif isinstance(step, Question):
                print()
                for num, q in zip(
                        range(1, len(step.questions) + 1), step.questions):
                    print("[{}]: {}".format(num, q))
                num = -1
                while not (1 <= num and num <= len(step.questions)):
                    try:
                        num = int(input('Your Answer: '))
                    except:
                        num = -1
                step.answer = num - 1
            elif isinstance(step, State):
                label, state = step.block_label, step.parameters
                if label is None:
                    print('-- Game Over --')
                    sys.exit(0)
                break
            else:
                assert(False)


if __name__ == '__main__':
    main()
