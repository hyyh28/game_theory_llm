from model import call_api
import argparse
from configuration import sequential_payoff_matrix
import time
from tqdm import tqdm
import json
import inflect
ordinal_converter = inflect.engine()

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

def depth_of_action_tree(dic, level = 0):
    if not isinstance(dic, dict) or not dic:
        return level
    return max(depth_of_action_tree(dic[key], level + 1)
                               for key in dic)

def get_all_actions(dic):
    actions = []
    if isinstance(dic, dict):
        actions.append(list(dic.keys()))
        for k in dic.keys():
            if isinstance(dic[k], dict):
                actions += get_all_actions(dic[k])
                break
    return actions
    

class Agent:
    def __init__(self, args, name):
        self.args = args 
        self.name = name
        self.the_other_player = 'Bob' if self.name == 'Alice' else 'Alice'
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []

        # game setting
        self.payoff_matrix = sequential_payoff_matrix[self.args.game]
        self.round_of_action = depth_of_action_tree(self.payoff_matrix)
        self.actions = get_all_actions(self.payoff_matrix)
        rule_descriptions = self.create_rule_description()
        self.game_setting = f"""
### Game Introduction

You are playing a sequential move game with another player to maximize the reward you can obtain. This game involves two players, Alice and Bob.
You are playing as {self.name}. You have different sets of actions to choose from for each round, same for the other player, {self.the_other_player}.

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
        def compute_action_sequence(actions):
            action_sequence = [[[]]]
            for round in range(len(actions)):
                buffer = []
                for current_sequence in action_sequence[-1]:
                    for action in actions[round]:
                        buffer.append(current_sequence + [action])
                action_sequence.append(buffer)
            return action_sequence
        action_sequences = compute_action_sequence(self.actions)
        rules = []
        ending_sequences = []
        for action_sequence in [a for action_list in action_sequences for a in action_list]:
            partial_dict = sequential_payoff_matrix[self.args.game].copy()
            bad_sequence = False
            for a in action_sequence:
                try:
                    partial_dict = partial_dict[a]
                except:
                    bad_sequence = True
            if isinstance(partial_dict, list) and not bad_sequence:
                ending_sequences.append(action_sequence)
                s = "If "
                for i, action in enumerate(action_sequence):
                    name = action[:action.index('_')]
                    a = action[action.index('_')+1:]
                    if i == 0:
                        s += f"{name} chooses {a}, "
                    else:
                        s += f"then {name} chooses {a}, "
                s += f"Alice will receive a reward of {partial_dict[0]} and Bob will receive a reward of {partial_dict[1]}."
                rules.append(s)
        self.action_sequences = ending_sequences
        return '\n'.join(rules)
    
    def make_action(self, previous_actions):
        # previous_actions: [Alice_choice_1, ...]
        payoff_matrix = self.payoff_matrix.copy()
        for a in previous_actions:
            a = a.replace('__', '_')
            payoff_matrix = payoff_matrix[a]
        actions = list(payoff_matrix.keys())
        action_text = [a[a.index('_'):] for a in actions]
        action_names = ', '.join(action_text)

        if not previous_actions:
            action_prompt = f"""
### Your Action

Analyse the problem and the negotiation message if there is any.
Please choose one of the following actions to maximize your reward.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.

Action choices: {action_names}
"""
        else:
            previous_actions = [(a[:a.index('_')], a[a.index('_')+1:]) for a in previous_actions]
            previous_actions = '. '.join([f"{name} chooses {action}" for name, action in previous_actions])
            action_prompt = f"""
### Previous Actions Done in the Game

The previous actions done in the game are presented below:
{previous_actions}
            
### Your Action

Analyse the problem and the negotiation message if there is any.
Please choose one of the following actions to maximize your reward.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.

Action choices: {action_names}
"""

        if self.previous_message:
            previous_messages = "\n### Negotiation Messages\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(self.previous_message)
            action_prompt = previous_messages + '\n' + action_prompt

            action_prompt = action_prompt + '\n\n' + self.prompt_for_negotiate[self.args.prompt_for_negotiate].format(self.the_other_player)

        action_prompt = self.game_setting + '\n' + action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                # print(action_message)
                # print('-'*20)
                action = parse_action(action_message, action_names)
                return action 
            except:
                time.sleep(0.1)

    def negotiate(self, previous_actions):
        if not previous_actions:
            negotiate_prompt = f"""
### Negotiation

You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player.

Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>'.
You can also choose the halt the negotiation by saying '<s>halt negotiation</s>'.
"""
        else:
            previous_actions = [(a[:a.index('_')], a[a.index('_')+1:]) for a in previous_actions]
            previous_actions = '. '.join([f"{name} chooses {action}" for name, action in previous_actions])
            negotiate_prompt = f"""
### Previous Actions Done in the Game

The previous actions done in the game are presented below:
{previous_actions}
            
### Negotiation

You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player.

Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>'.
You can also choose the halt the negotiation by saying '<s>halt negotiation</s>'.
"""

        if self.previous_message:
            previous_messages = "\n\n## The previous rounds of negotiation are presented below:\n\n" + '\n'.join(self.previous_message)
            negotiate_prompt += previous_messages

        negotiate_prompt = self.game_setting + negotiate_prompt

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message 
            except:
                time.sleep(0.1)
        
class Game:
    def __init__(self, args):
        self.args = args
        self.alice = Agent(args, 'Alice')
        self.bob = Agent(args, 'Bob')
        self.sequential_payoff_matrix = sequential_payoff_matrix[self.args.game]

    def play_next(self, player, previous_actions, action_number):
        for round in range(self.args.max_negotiation_round):
            if self.args.who_first == 'Alice':
                alice_message = self.alice.negotiate(previous_actions)
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice said in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                self.bob.previous_message.append('Alice said in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                bob_message = self.bob.negotiate(previous_actions)
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob replied in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                self.bob.previous_message.append('Bob replied in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
            else:
                bob_message = self.bob.negotiate(previous_actions)
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob said in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                self.bob.previous_message.append('Bob said in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                alice_message = self.alice.negotiate(previous_actions)
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice replied in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                self.bob.previous_message.append('Alice replied in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
        if player == 'Alice':
            action = self.alice.make_action(previous_actions)
        else:
            action = self.bob.make_action(previous_actions)
        return action
    
    def play(self):
        previous_actions = []
        action_number = 1
        while isinstance(self.sequential_payoff_matrix, dict):
            actions = list(self.sequential_payoff_matrix.keys())
            player = actions[0][:actions[0].index('_')]
            action = self.play_next(player, previous_actions, ordinal_converter.number_to_words(ordinal_converter.ordinal(action_number)))
            action = player + '_' + action
            action = action.replace('__', '_')
            previous_actions.append(action)
            self.sequential_payoff_matrix = self.sequential_payoff_matrix[action]
            action_number += 1

        return previous_actions



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='escalation_game', help="prisoner_dilemma, battle_of_sexes, stag_hunt, rock_paper_scissors")
    parser.add_argument('--max_negotiation_round', type=int, default=1)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    args = parser.parse_args()

    # alice_action, bob_action = game.play()
    # print(f'alice_action: {alice_action}')
    # print(f'bob_action: {bob_action}')

    result_save_dir = f'result/single_round/{args.game}_{args.max_negotiation_round}_{args.system_prompt}_negotationpromptnumber_{args.prompt_for_negotiate}.json'

    args.system_prompt = f'You are a {args.system_prompt} assistant that carefully answer the question.'
    decisions = []
    procedure = []
    for i in tqdm(range(args.sample_num)):
        game = Game(args)
        action_sequence = game.play()
        print(f'action sequence: {action_sequence}')
        procedure.append(game.alice.previous_message)
        decisions.append(action_sequence)

        # with open(result_save_dir, 'w') as f:
        #     json.dump({'decisions':decisions, 'negotiation':procedure}, f, indent=4)


