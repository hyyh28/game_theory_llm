from model import call_api
import argparse
from configuration import payoff_matrix, sequential_payoff_matrix
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

def parse_reason(message):
    assert '<r>' in message and '</r>' in message 
    start = message.index('<r>') + len('<r>')
    end = message.index('</r>')
    reason = message[start:end].strip('\n').strip()
    return reason

def parse_strategy(message):
    assert '<s>' in message and '</s>' in message 
    start = message.index('<s>') + len('<s>')
    end = message.index('</s>')
    reason = message[start:end].strip('\n').strip()
    return reason

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
        self.set_game()

        self.prompt_for_negotiate = {
            0:'', 
            1: "Please carefully analyze the negotiation messages, think about whether you can trust {} message, and make your own decision.\n",
            2: "Please carefully analyze the negotiation messages and make your own decision.\n",
            3: "You can choose your own choice regardless what {} says.\n",
            4: "You should make your own choice regardless what {} says.\n",
            5: "You must make your own choice regardless what {} says.\n",
            6: "Carefully analyze and think about whether you can trust {} message, and then make your own decision.\n",
        }

    def set_game(self):
        if self.args.game_type == 'simultaneous':
            self.payoff_matrix = payoff_matrix[self.args.game]
            self.my_actions = list(payoff_matrix[self.args.game][self.name].keys())
            self.the_other_actions = list(payoff_matrix[self.args.game][self.the_other_player].keys())
            rule_descriptions = self.create_simultaneous_rule_description()
            action_number = len(self.my_actions)
            self.action_names = ', '.join(self.my_actions)
            self.game_setting = f"""
### Game Introduction

You are playing a one-round game with another player to maximize the reward you can obtain. This game involves two players, Alice and Bob.
You are playing as {self.name}. You have {action_number} choices: {self.action_names}.
The other player, {self.the_other_player}, also has {action_number} choices: {self.action_names}.

### Game Rules

{rule_descriptions}
"""
        elif self.args.game_type == 'sequential':
            self.payoff_matrix = sequential_payoff_matrix[self.args.game]
            self.round_of_action = depth_of_action_tree(sequential_payoff_matrix[self.args.game])
            self.actions = get_all_actions(sequential_payoff_matrix[self.args.game])
            rule_descriptions = self.create_sequential_rule_description()
            self.game_setting = f"""
### Game Introduction

You are playing a sequential move game with another player to maximize the reward you can obtain. This game involves two players, Alice and Bob.
You are playing as {self.name}. You have different sets of actions to choose from for each round, same for the other player, {self.the_other_player}.

### Game Rules

{rule_descriptions}
"""
#             self.game_setting = f"""
# ### Game Introduction

# You are playing a number-guessing game with {self.args.number_of_players-1} other players.
# Guess a number in the range of [0,100] you think is the 2/3 of the average of all numbers that you and other players guess. 
# You will win the game if what you guess is the closest to 2/3 of the average than the numbers that others guessed.
# """
            
    def create_simultaneous_rule_description(self):
        sentences = []
        for choice_1 in self.my_actions:
            for choice_2 in self.the_other_actions:
                player_1_payoff = payoff_matrix[self.args.game][self.name][choice_1][self.the_other_player+"_"+choice_2]
                player_2_payoff = payoff_matrix[self.args.game][self.the_other_player][choice_2][self.name+"_"+choice_1]

                if choice_1 == choice_2:
                    r = f"- If both you and {self.the_other_player} choose {choice_1}, you will receive a reward of {player_1_payoff} and {self.the_other_player} will receive a reward of {player_2_payoff}."
                    sentences.append(r)
                elif choice_1 != choice_2:
                    r = f"- If you choose {choice_1} while {self.the_other_player} chooses {choice_2}, you will receive a reward of {player_1_payoff} and {self.the_other_player} will receive a reward of {player_2_payoff}."
                    sentences.append(r)
            sentences.append('\n')

        return '\n'.join(sentences)
    
    def create_sequential_rule_description(self):
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
    
    def sequential_game_workflow(self):
        def obtain_deepest_chains(sorted_action_sequences):
            max_len = len(sorted_action_sequences[-1])
            deepest_chains = []
            for chain in sorted_action_sequences:
                if len(chain) == max_len:
                    deepest_chains.append(chain[:-1])
            deepest_chains = [list(a) for a in list(set([tuple(a) for a in deepest_chains]))]
            return deepest_chains
        
        def update_current_tree(current_tree, chain, choice):
            temp_tree = current_tree.copy() 
            for k in chain:
                temp_tree = temp_tree[k]
            reward = temp_tree[choice]
            current_tree = json.loads(json.dumps(current_tree).replace(json.dumps(temp_tree), str(reward)))
            return current_tree
        
        def is_prefix(chain, decided_part):
            existent_chains = list(decided_part.keys())
            prefixes = []
            for existent_chain in existent_chains:
                if str(existent_chain)[1:-1].startswith(str(chain)[1:-1]):
                    prefixes.append(existent_chain)
            if prefixes:
                return prefixes
            return None
        
        current_action_sequences = self.action_sequences
        sorted_action_sequences = sorted(current_action_sequences, key=lambda x: len(x))
        current_tree = sequential_payoff_matrix[self.args.game]
        decided_part = {}
        while not isinstance(current_tree, list):
            # find the longest decision tree chain
            deepest_chains = obtain_deepest_chains(sorted_action_sequences)
            for chain in deepest_chains:
                temp_tree = current_tree.copy()
                for k in chain:
                    temp_tree = temp_tree[k]
                # available choices
                choices = list(temp_tree.keys())
                # the player who should make the decision
                player = choices[0].split('_')[0]
                if not is_prefix(chain, decided_part):
                    decided_choice, reason = self.chain_conditioned_actions(player, chain, choices)
                else:
                    decided_choice, reason = self.chain_conditioned_actions_with_decisions_made(player, chain, choices, decided_part)
                
                # update the decision tree
                if is_prefix(chain, decided_part) and tuple(chain + [player + '_' + decided_choice]) in decided_part:
                    prefixes = is_prefix(chain, decided_part)
                    decided_part[tuple(chain)] = [(player, decided_choice, reason)] + decided_part[tuple(chain + [player + '_' + decided_choice])]
                    for prefix_chain in prefixes:
                        decided_part.pop(prefix_chain)
                elif is_prefix(chain, decided_part) and not tuple(chain + [player + '_' + decided_choice]) in decided_part:
                    prefixes = is_prefix(chain, decided_part)
                    decided_part[tuple(chain)] = [(player, decided_choice, reason)]
                    for prefix_chain in prefixes:
                        decided_part.pop(prefix_chain)
                else:
                    decided_part[tuple(chain)] = [(player, decided_choice, reason)]

                # remove the decided part of the decision tree
                current_tree = update_current_tree(current_tree, chain, player+'_'+decided_choice)
                
                # update the action sequences, sorted action sequences
                for choice in choices:
                    current_action_sequences.remove(chain + [choice])
                current_action_sequences.append(chain)
                sorted_action_sequences = sorted(current_action_sequences, key=lambda x: len(x))

        # convert decision tree to text to generate strategy
        thinking_chains = list(decided_part.values())[0]
        for i in range(len(thinking_chains)):
            ordinal_number = ordinal_converter.number_to_words(ordinal_converter.ordinal(i+1)).capitalize()
            thinking_chains[i] = f'{ordinal_number}, {thinking_chains[i][0]} will choose {thinking_chains[i][1]} because {thinking_chains[i][2]}.' if thinking_chains[i][0] != self.name else f'{ordinal_number}, I will choose {thinking_chains[i][1]} because {thinking_chains[i][2]}.'       
        
        # convert the decision tree to a summarized strategy
        summarized_strategy, thoughts = self.summarizer(thinking_chains)

        return summarized_strategy, thoughts

    def simultaneous_game_workflow(self):
        player_perspective_choices = {}
        player_perspective_thinking_chains = []
        for player in ['Alice', 'Bob']:
            player_perspective_choices[player] = []
            if player == self.name:
                for your_action in self.my_actions:
                    other_action, other_action_reason = self.other_conditioned_action(your_action)
                    player_perspective_choices[player].append((your_action, other_action))
                    other_action_reason = self.perspective_wise_reasoning_template(player, your_action, other_action, other_action_reason)
                    player_perspective_thinking_chains.append(other_action_reason)
            else:
                for other_action in self.the_other_actions:
                    your_action, your_action_reason = self.your_conditioned_action(other_action)
                    player_perspective_choices[player].append((your_action, other_action))
                    your_action_reason = self.perspective_wise_reasoning_template(player, other_action, your_action, your_action_reason)
                    player_perspective_thinking_chains.append(your_action_reason)

        # pure_strategy_NE = self.get_pure_strategy_NE(player_perspective_choices)
        # print(pure_strategy_NE)
        # print('-'*20)
        summarized_strategy = self.summarizer(player_perspective_thinking_chains)
        # print(summarized_strategy)
        # print('*'*20)
        return summarized_strategy

    def other_conditional_reasoning_template(self, condition, action, reason):
        template = f"""
If {self.the_other_player} thinks that I choose {condition}, {self.the_other_player} will choose {action} because {reason}.
"""
        return template
    
    def your_conditional_reasoning_template(self, condition, action, reason):
        template = f"""
If I think {self.the_other_player} chooses {condition}, then I will choose {action} because {reason}.
"""
        return template

    def perspective_wise_reasoning_template(self, player, condition, action, reason):
        if player != self.name:
            template = f"""
If {self.the_other_player} chooses {condition}, then I will choose {action} because {reason}.
"""
        else:
            template = f"""
If I chooses {condition}, then {self.the_other_player} will choose {action} because {reason}.
"""
        return template

    def chain_conditioned_actions(self, player, chain, actions):
        chain = [[action.split('_')[0], action[action.index('_')+1:]] for action in chain]
        chain = [f"{name} chooses {action}." for name, action in chain]
        text_chain = ''
        for i, one in enumerate(chain):
            if i == 0:
                text_chain += 'First, ' + one
            else:
                text_chain += '\nThen '+ one
        text_actions = ', '.join([action.replace(player+'_', '') for action in actions])
        if player == self.name:
            conditioned_action_prompt = f"""
### Your Potential Action Given Previous Actions

Suppose the previous actions are: {text_chain}.
There are two possible actions that you can take: {text_actions}

What action would you then take to maximize your reward and why?
Analyze the game rules and the current situation of their choice and then infer your best choice.

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you make the choice. For example, '<r>I choose choice_1 because ...</r>'.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
        else:
            conditioned_action_prompt = f"""
### The Other Player's Potential Action Given Previous Actions

Suppose the previous actions are: {text_chain}.
There are two possible actions that {self.the_other_player} can take: {text_actions}

What action do you think {self.the_other_player} will take to maximize their reward and why?
Analyze the game rules based on your choice, and then infer their optimal choice that maximizes their reward conditionally.

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you think they may make the choice. For example, '<r>I think {self.the_other_player} would choose choice_1 because ...</r>'.
Surround your inference result with '<s>' and '</s>' to indicate the start and end. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
            
        action_prompt = self.game_setting + '\n' + conditioned_action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                action = parse_action(action_message, text_actions)
                reason = parse_reason(action_message)
                return action, reason
            except:
                time.sleep(0.1)

    def chain_conditioned_actions_with_decisions_made(self, player, chain, actions, decided_part):
        # def search_prefix_action(chain, actions, decided_part):
        #     for i in range(len(chain)):
        #         prefix = chain[:i]
        #         if tuple(prefix) in decided_part:
        #             return decided_part[tuple(prefix)][0]
        #     return None
        _text_chain = [[action.split('_')[0], action[action.index('_')+1:]] for action in chain]
        _text_chain = [f"{name} chooses {action}." for name, action in _text_chain]
        text_chain = ''
        for i, one in enumerate(_text_chain):
            if i == 0:
                text_chain += 'First, ' + one
            else:
                text_chain += '\nThen '+ one
        text_actions = ', '.join([action.replace(player+'_', '') for action in actions])

        # prefix_action = search_prefix_action(chain, actions, decided_part)
        # decisions_will_be_made = decided_part[tuple(chain+[action])]
        choice_result_text = ''
        for action in actions:
            a = action.replace(player+'_', '')
            choice_result_text += f'Notice that if you choose {a}, ' if player == self.name else f'Notice that if {player} choose {a}, '
            if tuple(chain+[action]) in decided_part:
                decisions_will_be_made = decided_part[tuple(chain+[action])]
                for decision_will_be_made in decisions_will_be_made:
                    choice_result_text += f"you will choose {decision_will_be_made[1]} because {decision_will_be_made[2]}.\n" if decision_will_be_made[0] == self.name else f"{decision_will_be_made[0]} will choose {decision_will_be_made[1]} because {decision_will_be_made[2]}.\n"
            else:
                choice_result_text += "the game will finish with rewards obtained defined by the game rules."
        if player == self.name:
            conditioned_action_prompt = f"""
### Your Potential Action Given Previous Actions

Suppose the previous actions are: {text_chain}.
There are two possible actions that you can take: {text_actions}

{choice_result_text}

What action would you then take to maximize your reward and why?
Analyze the game rules and the current situation of their choice and then infer your best choice.

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you make the choice. For example, '<r>I choose choice_1 because ...</r>'.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
        else:
            conditioned_action_prompt = f"""
### The Other Player's Potential Action Given Previous Actions

Suppose the previous actions are: {text_chain}.
There are two possible actions that {self.the_other_player} can take: {text_actions}

{choice_result_text}

What action do you think {self.the_other_player} will take to maximize their reward and why?
Analyze the game rules based on your choice, and then infer their optimal choice that maximizes their reward conditionally.

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you think they may make the choice. For example, '<r>I think {self.the_other_player} would choose choice_1 because ...</r>'.
Surround your inference result with '<s>' and '</s>' to indicate the start and end. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
        
        action_prompt = self.game_setting + '\n' + conditioned_action_prompt
        action_prompt = action_prompt.replace('I ', 'you ').replace('my ', 'your ')

        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                action = parse_action(action_message, text_actions)
                reason = parse_reason(action_message)
                return action, reason
            except:
                time.sleep(0.1)

    def your_conditioned_action(self, other_action):
        conditional_action_prompt = f"""
### Your Potential Action Given the Other Player's Action

Suppose {self.the_other_player} has chosen to take the action: {other_action}.
What action would you then take to maximize your reward and why?
Analyze the game rules and the current situation of their choice and then infer your best choice.

There are two possible actions that you can take:
{self.action_names}

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you make the choice. For example, '<r>I choose choice_1 because ...</r>'.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
        action_prompt = self.game_setting + '\n' + conditional_action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                action = parse_action(action_message, self.my_actions)
                reason = parse_reason(action_message)
                return action, reason
            except:
                time.sleep(0.1)

    def other_conditioned_action(self, your_action):
        conditional_action_prompt = f"""
### The Other Player's Action Given Your Action

Suppose you have chosen to take the action: {your_action}.
There are two possible actions that {self.the_other_player} can take:
{self.action_names}

What action do you think {self.the_other_player} will take to maximize their reward and why?
Analyze the game rules based on your choice, and then infer their optimal choice that maximizes their reward conditionally.

Surround your reasoning with '<r>' and '</r>' to indicate the start and end of why you think they may make the choice. For example, '<r>I choose {self.the_other_player} would choose choice_1 because ...</r>'.
Surround your inference result with '<s>' and '</s>' to indicate the start and end. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
"""
        action_prompt = self.game_setting + '\n' + conditional_action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                action = parse_action(action_message, self.my_actions)
                reason = parse_reason(action_message)
                return action, reason
            except:
                time.sleep(0.1)

    def make_simultaneous_action(self):
        action_prompt = f"""
### Your Action

Analyse the problem and the negotiation message if there is any.
Please choose one of the following actions to maximize your reward.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.

Action choices: {self.action_names}
"""
        if self.previous_message:
            previous_messages = "\n### Negotiation Messages\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(self.previous_message)
            action_prompt = previous_messages + '\n' + action_prompt

            action_prompt = action_prompt + '\n\n' + self.prompt_for_negotiate[self.args.prompt_for_negotiate].format(self.the_other_player)

        action_prompt = self.game_setting + '\n' + self.strategy_summary + '\n' + action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                action = parse_action(action_message, self.my_actions)
                return action 
            except:
                time.sleep(0.1)
        
    def simultaneous_negotiate(self):
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

        negotiate_prompt = self.game_setting + '\n' + self.strategy_summary + '\n' + negotiate_prompt

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message 
            except:
                time.sleep(0.1)

    def make_sequential_action(self, previous_actions):
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
            previous_actions = [(a[:a.index('_')], a[a.index('_'):]) for a in previous_actions]
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

        action_prompt = self.game_setting + '\n' + self.strategy_summary+ '\n' + self.strategy_thoughts + '\n' + action_prompt
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                # print(action_message)
                # print('-'*20)
                action = parse_action(action_message, action_names)
                return action 
            except:
                time.sleep(0.1)

    def sequential_negotiate(self, previous_actions):
        if not previous_actions:
            negotiate_prompt = f"""
### Negotiation

You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player.

Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>'.
You can also choose the halt the negotiation by saying '<s>halt negotiation</s>'.
"""
        else:
            previous_actions = [(a[:a.index('_')], a[a.index('_'):]) for a in previous_actions]
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
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(self.previous_message)
            negotiate_prompt += previous_messages

        negotiate_prompt = self.game_setting + '\n' + self.strategy_summary+ '\n' + self.strategy_thoughts + '\n' + negotiate_prompt

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message 
            except:
                time.sleep(0.1)
  
    def get_pure_strategy_NE(self, player_perspective_choices):
        NE = list(set(list(player_perspective_choices.values())[0]).intersection(set(list(player_perspective_choices.values())[1])))
        number_of_NE = len(NE)
        NE_prompt = f"""
### Pure Strategy Nash Equilibrium

From the analysis of the game, we can find the pure strategy Nash equilibrium of the game. 
There are {number_of_NE} pure strategy Nash equilibrium(s) in the game:

"""
        for i, ne in enumerate(NE):
            NE_prompt += f"""
Pure Strategy Nash Equilibrium {i+1}: {self.name} chooses {ne[0]} and {self.the_other_player} chooses {ne[1]}.
"""

        return NE_prompt

    def get_strategy_in_support_of_NE(self, branching_choices):
        pure_strategies = []
        for k,v in branching_choices.items():
            pure_strategies.append(v[-1])
        pure_strategies = list(set(pure_strategies))
        return pure_strategies 
    
    def check_pure_strategy_NE(self, branching_choices):
        pure_strategies_IS_NE = self.get_strategy_in_support_of_NE(branching_choices)
        pure_NE = {}
        for pure_strategy in pure_strategies_IS_NE:
            pure_NE[pure_strategy] = False
            your_action = pure_strategy
            
            other_conditioned_action, _ = self.other_conditioned_action(your_action)
            others_action = other_conditioned_action

            your_conditioned_action, _ = self.your_conditioned_action(others_action)

            # check if the action starts to loop
            if your_conditioned_action  == pure_strategy:
                pure_NE[pure_strategy] = True
        return pure_NE

    def summarizer(self, thinking_chains):
        def beautify_strategy(strategy):
            return f"""
### Strategy You Have Derived

You have thought about the game and derived the following strategy:
{strategy}

If you need to negotiate with the other player:
Keep this strategy in mind;
Think about what to tell the other player in order for you to obtain most reward based on your calculation in the strategy.

If you need to make decisions:
Follow this strategy to maximize your reward.
"""
        
        thoughts = '\n'.join(thinking_chains)
        summary_prompt = f"""
### Summary of Thinking Chains

Below are the thinking processes that you have gone through about: 
(1) your decisions conditioned on the other player's actions 
(2) guesses of others' decisions conditioned on your actions.

Carefully analyze the thinking chains step by step.
Then summarize the thinking chains into a strategy that you can take in the game without any conditional knowledge such as the other player's action.
The strategy can be one specific action or a probability distribution of actions.

{thoughts}

Surround the strategy you have derived from the thinking chains using '<s>' and '</s>' to indicate the start and end of your strategy. For example, '<s>always choose choice_1</s>' or '<s>always choose choice_2</s>'.
"""
        summary_prompt = self.game_setting + '\n' + summary_prompt
        while True:
            try:
                strategy_message = call_api(self.args.model, summary_prompt, self.args.system_prompt)
                print(strategy_message)
                strategy = parse_strategy(strategy_message)
                print(strategy)
                return beautify_strategy(strategy), thoughts
            except:
                time.sleep(0.1)

    def get_strategy(self, pure_strategies):
        # If a mixed strategy is played in a Nash equilibrium
        # all pure strategies in the support of that mixed strategy must yield an equal expected payoff
        pass

class Simultaneous_Game:
    def __init__(self, args):
        self.args = args
        self.alice = Agent(args, 'Alice')
        self.alice.strategy_summary, _ = self.alice.simultaneous_game_workflow()
        self.bob = Agent(args, 'Bob')
        self.bob.strategy_summary, _ = self.bob.simultaneous_game_workflow()

    def play(self):        
        for round in range(self.args.max_negotiation_round):
            if self.args.who_first == 'Alice':
                alice_message = self.alice.simultaneous_negotiate()
                # print('**Alice says:**')
                # print(alice_message)
                # print('='*20)
                if alice_message == 'halt negotiation':
                    break
                self.alice.previous_message.append('Alice said in round {}: '.format(round+1)+alice_message)
                self.bob.previous_message.append('Alice said in round {}: '.format(round+1)+alice_message)
                bob_message = self.bob.simultaneous_negotiate()
                # print('**Bob says:**')
                # print(bob_message)
                # print('='*20)
                if bob_message == 'halt negotiation':
                    break
                self.alice.previous_message.append('Bob replied in round {}: '.format(round+1)+bob_message)
                self.bob.previous_message.append('Bob replied in round {}: '.format(round+1)+bob_message)
            else:
                bob_message = self.bob.simultaneous_negotiate()
                if bob_message == 'halt negotiation':
                    break
                self.alice.previous_message.append('Bob said in round {}: '.format(round+1)+bob_message)
                self.bob.previous_message.append('Bob said in round {}: '.format(round+1)+bob_message)
                alice_message = self.alice.simultaneous_negotiate()
                if alice_message == 'halt negotiation':
                    break
                self.alice.previous_message.append('Alice replied in round {}: '.format(round+1)+alice_message)
                self.bob.previous_message.append('Alice replied in round {}: '.format(round+1)+alice_message)
        alice_action = self.alice.make_simultaneous_action()
        print(alice_action)
        bob_action = self.bob.make_simultaneous_action()
        print(bob_action)
        return alice_action, bob_action

class Sequential_Game:
    def __init__(self, args):
        self.args = args
        self.alice = Agent(args, 'Alice')
        self.bob = Agent(args, 'Bob')
        self.sequential_payoff_matrix = sequential_payoff_matrix[self.args.game]
        self.alice.strategy_summary, self.alice.strategy_thoughts = self.alice.sequential_game_workflow()
        self.bob.strategy_summary, self.bob.strategy_thoughts = self.bob.sequential_game_workflow()

    def play_next(self, player, previous_actions, action_number):
        for round in range(self.args.max_negotiation_round):
            if self.args.who_first == 'Alice':
                alice_message = self.alice.sequential_negotiate(previous_actions)
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice said in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                self.bob.previous_message.append('Alice said in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                bob_message = self.bob.sequential_negotiate(previous_actions)
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob replied in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                self.bob.previous_message.append('Bob replied in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
            else:
                bob_message = self.bob.sequential_negotiate(previous_actions)
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob said in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                self.bob.previous_message.append('Bob said in round {} before the {} action:\n'.format(round+1, action_number)+bob_message)
                alice_message = self.alice.sequential_negotiate(previous_actions)
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice replied in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
                self.bob.previous_message.append('Alice replied in round {} before the {} action:\n'.format(round+1, action_number)+alice_message)
        if player == 'Alice':
            action = self.alice.make_sequential_action(previous_actions)
        else:
            action = self.bob.make_sequential_action(previous_actions)
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
    parser.add_argument('--game', type=str, default='draco', help="prisoner_dilemma, battle_of_sexes, stag_hunt_small, rock_paper_scissors, IESDS, imbalanced_actions, duopolistic_competition, escalation_game, monopoly_game, draco, trigame, hot_cold_game")
    parser.add_argument('--game_type', type=str, default='sequential', help="simultaneous or sequential")
    parser.add_argument('--max_negotiation_round', type=int, default=0)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    args = parser.parse_args()

    # alice = Agent(args, 'Alice')
    # alice.sequential_game_workflow()
    bob = Agent(args, 'Bob')
    bob.sequential_game_workflow()

    game = Simultaneous_Game(args)
    alice_action, bob_action = game.play()
