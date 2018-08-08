import json
import random


class Riddler(object):
    def __init__(self, turns):
        self.riddles = self._get_riddles()
        self.current_turn = 0
        self.total_turns = turns
        self.current_riddle = None
        self.stopped = False
        self.scores = {}

    @staticmethod
    def _get_riddles():
        with open("riddles.txt", "r") as f:
            return json.load(f)

    def random_riddle(self):
        new_riddle = random.choice(self.riddles)
        while self.current_riddle == new_riddle:
            new_riddle = random.choice(self.riddles)
        self.current_riddle = new_riddle
        return self.current_riddle

    def is_correct(self, answer):
        return self.current_riddle[1].lower() == answer.lower()

    def set_score(self, name):
        try:
            self.scores[name] += 1
        except KeyError:
            self.scores[name] = 1
        self.current_turn += 1

    def has_ended(self):
        return self.current_turn > self.total_turns

    def highscores(self):
        hiscore = [(name, self.scores[name]) for name in sorted(self.scores, key=self.scores.get, reverse=True)]
        return hiscore

    def start(self, turns):
        return self.random_riddle()

    def stop(self):
        self.stopped = True
