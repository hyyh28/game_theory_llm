from model import close_source_call
import argparse
import time
from tqdm import tqdm
import json

def parse(message):
    assert '<s>' in message and '</s>' in message 
    start = message.index('<s>') + len('<s>')
    end = message.index('</s>')
    return message[start:end]

def parse_action(message, choices):
    assert '<s>' in message and '</s>' in message 
    start = message.index('<s>') + len('<s>')
    end = message.index('</s>')
    action = message[start:end].strip('\n').strip()
    assert action in choices
    return message[start:end]

# max/2,max/2 | 0, max
# max, 0      | 0, 0
def create_payoff_matrix(args):
    payoff_matrix = {
        'Alice': 
            {
                'choice_1': 
                {
                    'Bob_choice_1': args.max/2,
                    'Bob_choice_2': 0
                }, 
                'choice_2': 
                {
                    'Bob_choice_1': args.max, 
                    'Bob_choice_2': 0
                }
            },
        'Bob': 
            {
                'choice_1': 
                {
                    'Alice_choice_1': args.max/2,
                    'Alice_choice_2': 0
                }, 
                'choice_2': 
                {
                    'Alice_choice_1': args.max, 
                    'Alice_choice_2': 0
                }
            },
    }   
    return payoff_matrix

class Agent:
    def __init__(self, args, name):
        self.args = args 
        self.name = name
        self.the_other_player = 'Bob' if self.name == 'Alice' else 'Alice'
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []
        self.payoff_matrix = create_payoff_matrix(args)

        # game setting
        self.actions = list(self.payoff_matrix[self.name].keys())
        action_number = len(self.actions)
        self.action_names = ', '.join(self.actions)
        rule_descriptions = self.create_rule_description()
        self.game_setting = f"""
### Game Introduction

You are playing a one-round game with another player to maximize the money reward you can obtain. This game involves two players, Alice and Bob.
You are playing as {self.name}. You have {action_number} choices: {self.action_names}.
The other player, {self.the_other_player}, also has {action_number} choices: {self.action_names}.

### Game Rules

{rule_descriptions}
"""
        self.prompt_for_negotiate = {
            0:'', 
            1: "Please carefully analyze the negotiation messages, think about whether you can trust {} message, and make your own decision.\n",
            2: "Please carefully analyze the negotiation messages and make your own decision.\n",
            3: "You can choose your own choice regardless what {} says.\n",
            4: "You should make your own choice regardless what {} says.\n",
            5: "You must make your own choice regardless what {} says.\n",
            6: "Carefully analyze and think about whether you can trust {} message, and then make your own decision.\n",
        }

    def create_rule_description(self):
        sentences = []
        for choice_1 in self.actions:
            for choice_2 in self.actions:
                player_1_payoff = self.payoff_matrix[self.name][choice_1][self.the_other_player+"_"+choice_2]
                player_2_payoff = self.payoff_matrix[self.the_other_player][choice_2][self.name+"_"+choice_1]
                if choice_1 == choice_2:
                    r = f"- If both you and {self.the_other_player} choose {choice_1}, you will receive a reward of ${player_1_payoff} and {self.the_other_player} will receive a reward of ${player_2_payoff}."
                    sentences.append(r)
                elif choice_1 != choice_2:
                    r = f"- If you choose {choice_1} while {self.the_other_player} chooses {choice_2}, you will receive a reward of ${player_1_payoff} and {self.the_other_player} will receive a reward of ${player_2_payoff}."
                    sentences.append(r)
            sentences.append('\n')
        return '\n'.join(sentences)

    def make_action(self):
        action_prompt = f"""
### Your Action

Analyse the problem and the negotiation message if there is any.
Please choose one of the following actions to maximize your reward (money).
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.

Action choices: {self.action_names}
"""
        if self.previous_message:
            previous_messages = "\n### Negotiation Messages\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(self.previous_message)
            action_prompt = previous_messages + '\n' + action_prompt

            action_prompt = action_prompt + '\n\n' + self.prompt_for_negotiate[self.args.prompt_for_negotiate].format(self.the_other_player)

        action_prompt = self.game_setting + '\n' + action_prompt
        while True:
            try:
                action_message = close_source_call('claude', action_prompt, self.args.system_prompt)
                action = parse_action(action_message, self.actions)
                return action 
            except:
                time.sleep(0.1)
        

    def negotiate(self):
        negotiate_prompt = f"""
### Negotiation

You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player.

Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>'.
You can also choose the halt the negotiation by saying '<s>halt negotiation</s>'.
"""
        if self.previous_message:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + negotiate_prompt
        while True:
            try:
                message = close_source_call('claude', negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message 
            except:
                time.sleep(0.1)
        

class Game:
    def __init__(self, args):
        self.args = args
        self.alice = Agent(args, 'Alice')
        self.bob = Agent(args, 'Bob')

    def play(self):
        for round in range(self.args.max_negotiation_round):
            if self.args.who_first == 'Alice':
                alice_message = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice said in round {}: '.format(round+1)+alice_message)
                self.bob.previous_message.append('Alice said in round {}: '.format(round+1)+alice_message)
                bob_message = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob replied in round {}: '.format(round+1)+bob_message)
                self.bob.previous_message.append('Bob replied in round {}: '.format(round+1)+bob_message)
            else:
                bob_message = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob said in round {}: '.format(round+1)+bob_message)
                self.bob.previous_message.append('Bob said in round {}: '.format(round+1)+bob_message)
                alice_message = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice replied in round {}: '.format(round+1)+alice_message)
                self.bob.previous_message.append('Alice replied in round {}: '.format(round+1)+alice_message)
        alice_action = self.alice.make_action()
        bob_action = self.bob.make_action()
        return alice_action, bob_action


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', type=int, default=100, help="100 - 100,150")
    parser.add_argument('--max_negotiation_round', type=int, default=0)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=20)
    parser.add_argument('--personality', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    args = parser.parse_args()

    # alice_action, bob_action = game.play()
    # print(f'alice_action: {alice_action}')
    # print(f'bob_action: {bob_action}')

    presonalities = ['helpful', 'compassionate', 'witty', 'pragmatic']
    for personality in presonalities:
        args.personality = personality
        money_rewards = [250,500,1000,1500,2000,2500,5000,10000,15000,20000,25000,50000,100150]
        for money in money_rewards:
            args.max = money
            result_save_dir = f'result/human_verification/{args.personality}_{args.max}_2.json'
            print('='*10)
            print(result_save_dir)
            print('='*10)
            args.system_prompt = f'You are a {args.personality} assistant that carefully answer the question.'
            
            # run process
            decisions = []
            for i in tqdm(range(args.sample_num)):
                game = Game(args)
                alice_action, bob_action = game.play()
                print(f'alice_action: {alice_action}')
                print(f'bob_action: {bob_action}')
                decisions.append({'Alice_action':alice_action, 'Bob_action':bob_action})

                with open(result_save_dir, 'w') as f:
                    json.dump({'decisions':decisions, 'negotiation':[]}, f, indent=4)


        