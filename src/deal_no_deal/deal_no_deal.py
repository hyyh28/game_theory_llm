import sys
sys.path.append('../')

import random
import argparse
import numpy as np
from tqdm import tqdm
from model import call_api
import time 
from deal_no_deal_metrics import (
    gen_choices,
    check_pareto_optimalities,
    compute_score,
    translate_values,
    check_envy_free,
    check_envy_free_pareto_optimal,
    check_human_pareto_optimal_envy_free,
    have_envy_free_solution
)
import json
import config

### data processing
def process_data(data):
    def parse_agent1_input(line):
        start = line.index('<input>') + len('<input>')
        end = line.index('</input>')
        example_count = [int(a) for i,a in enumerate([a.strip() for a in line[start:end].split(' ')[1:-1]]) if i % 2 == 0]
        agent1_values = [int(a) for i,a in enumerate([a.strip() for a in line[start:end].split(' ')[1:-1]]) if i % 2 == 1]
        agent1_values_text = translate_values(example_count, agent1_values)
        return example_count, agent1_values, agent1_values_text
    
    def parse_agent2_input(line):
        start = line.index('<partner_input>') + len('<partner_input>')
        end = line.index('</partner_input>')
        example_count = [int(a) for i,a in enumerate([a.strip() for a in line[start:end].split(' ')[1:-1]]) if i % 2 == 0]
        agent2_values = [int(a) for i,a in enumerate([a.strip() for a in line[start:end].split(' ')[1:-1]]) if i % 2 == 1]
        agent2_values_text = translate_values(example_count, agent2_values)
        return example_count, agent2_values, agent2_values_text
    
    def parse_human_outcome(line):
        start = line.index('<output>') + len('<output>')
        end = line.index('</output>')
        outcomes = [a.strip() for a in line[start:end].split(' ')[1:-1]]
        if 'item0=' in outcomes[0]:
            agent1_outcomes = [int(a.split('=')[1]) for a in outcomes[:3]]
            agent2_outcomes = [int(a.split('=')[1]) for a in outcomes[3:]]
            return agent1_outcomes, agent2_outcomes
        else:
            return outcomes[:3], outcomes[3:]

    example_count, agent1_values, agent1_values_text = parse_agent1_input(data)
    example_count, agent2_values, agent2_values_text = parse_agent2_input(data)
    agent1_human_outcomes, agent2_human_outcomes = parse_human_outcome(data)

    return example_count, agent1_values, agent1_values_text, agent2_values, agent2_values_text, agent1_human_outcomes, agent2_human_outcomes

def parse(message):
    print(message)
    assert '<s>' in message and '</s>' in message 
    starts = [i for i in range(len(message)) if message[i:i+len('<s>')] == '<s>']
    ends = [i for i in range(len(message)) if message[i:i+len('</s>')] == '</s>']
    start = starts[0] + len('<s>')
    end = ends[-1]
    return message[start:end]

def parse_deal(message):
    assert '<deal>' in message and '</deal>' in message
    start = message.index('<deal>') + len('<deal>')
    end = message.index('</deal>')
    deal = message[start:end]
    deal = deal.split(' ')
    deal = [int(a.split('=')[1]) for a in deal]
    return deal

def parse_value(message):
    assert '<value>' in message and '</value>' in message
    start = message.index('<value>') + len('<value>')
    end = message.index('</value>')
    deal = message[start:end]
    deal = deal.split(' ')
    deal = [int(a.split('=')[1]) for a in deal]
    return deal

def parse_strategy(message):
    strategies = []
    assert '<strategy1>' in message and '</strategy1>' in message
    for i in range(1, 65):
        if f'<strategy{i}>' in message and f'</strategy{i}>' in message:
            start = message.index(f'<strategy{i}>') + len(f'<strategy{i}>')
            end = message.index(f'</strategy{i}>')
            strategy = message[start:end]
            strategy = strategy.split(' ')
            strategy = [int(a.split('=')[1]) for a in strategy]
            strategies.append(strategy)
    return strategies


class Agent:
    def __init__(self, args, data, name):
        (self.example_count, 
         self.agent1_values, 
         self.agent1_values_text, 
         self.agent2_values, 
         self.agent2_values_text,
         self.agent1_human_outcomes, 
         self.agent2_human_outcomes) = process_data(data)
        self.args = args
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []
        self.my_previous_proposals = []
        self.the_other_player_previous_proposals = []

        self.value_guesses = []

        self.possible_values = None
        
        self.name = name
        self.the_other_player = 'Bob' if self.name == 'Alice' else 'Alice'
        self.game_setting()
    
    def game_setting(self):
        if self.name == 'Alice':
            self.agent_values = self.agent1_values
        else:
            self.agent_values = self.agent2_values
        if self.args.special_prompting:
            self.game_description = f"""
### Game Description

This is a negotiation game. There are {self.example_count[0]} books, {self.example_count[1]} hats, and {self.example_count[2]} balls in total. 
Each item has a value to you and {self.the_other_player} which is unknown to you and can be very different from yours.
Thus do not assume the value of the items to {self.the_other_player} is the same as yours.

Your goal is to MAXIMIZE the total VALUE you alone can obtain by taking the items after negotiation.
You need to negotiate with {self.the_other_player} to decide which and how many items you and your {self.the_other_player} will each get.
DO NOT REVEAL your values of the items to {self.the_other_player} through out the game.
Notice that if you come to disagreement on the negotiation, neither of you will obtain any reward.

You are playing the role of {self.name}. The player you negotiate with is {self.the_other_player}.

### Pareto Optimality and Envy Freeness Principles

There are two principles you need to consider when negotiating the deal with your {self.the_other_player}: 

(1) pareto optimality: a deal is pareto optimal if there is no other deal that makes both you and your the other player better off.
e.g. Imagine Alice and Bob are dividing an 8-slice pizza, both liking all slices equally. Deal 1, where each gets 4 slices, is Pareto optimal as no other deal improves both players' outcomes without worsening one's. Deal 2, with Alice getting 3 slices and Bob 4, is not Pareto optimal since an equal split makes both better off or at least not worse off.

(2) envy freeness: a deal is envy free if each person receive items that are, in their eyes, at least as valuable as the share received by your the other player.
e.g. Alice and Bob are dividing a book, a toy, and a candy bar; Alice prefers the book, then toy, then candy bar, while Bob prefers the toy, then candy bar, then book. Deal 1, where Alice gets the book and Bob gets the toy and candy bar, is envy-free as both prefer their shares. Deal 2, with Alice getting the toy and Bob the book and candy bar, is not envy-free as both would prefer the other's share.

Pareto optimality and envy-freeness are beneficial for negotiations as they promote efficiency and fairness, respectively. These principles enhance stability and mutual satisfaction, reducing the likelihood of resentment or renegotiation. By ensuring that resources are allocated effectively and that all parties feel fairly treated, they foster productive and harmonious relationships.
Remember, DO NOT REVEAL your values of the items to {self.the_other_player} through out the game.

### Item Values to You

{translate_values(self.example_count, self.agent_values)}

Thus, the highest total value you could obtain is {compute_score(self.agent_values, self.example_count)} by taking all items.
"""
        else:
            self.game_description = f"""
### Game Description

This is a negotiation game. There are {self.example_count[0]} books, {self.example_count[1]} hats, and {self.example_count[2]} balls in total. 
Each item has a value (range minimum 0 - maximum 10) to you and {self.the_other_player} which is unknown to you and can be very different from yours.
And you only know that sum of all values of all items to both playes is 10.
Thus do not assume the value of the items to {self.the_other_player} is the same as yours.

Your goal is to MAXIMIZE the total VALUE you alone can obtain by taking the items after negotiation (NOTICE THAT SINGLE ITEM CANNOT BE SPLITTED).
You need to negotiate with {self.the_other_player} to decide which and how many items you and your partner {self.the_other_player} will each get.
DO NOT REVEAL your values of the items to {self.the_other_player} through out the game.
Notice that if you come to disagreement on the negotiation, neither of you will obtain any reward.

You are playing the role of {self.name}. The player you negotiate with is {self.the_other_player}.

### Item Values to You

{translate_values(self.example_count, self.agent_values)}

Thus, the highest total value you could obtain is {compute_score(self.agent_values, self.example_count)} by taking all items.
"""

    def present_deal(self):
        present_deal_prompt = f"""
### Present Deal

You have finished the negotiation. Now, you need to present the deal to the other player.
You need to present which and how many items you will get based on your negotiation.
Write down the number of books, hats, and balls you want to get in the format of <deal>book=x hat=y ball=z</deal>, where x, y, and z are the number of books, hats, and balls you want to get, respectively.
""" 
        previous_messages = "\n\n## The previous rounds of negotiation are presented below:\n\n" + '\n'.join(self.previous_message)
        
        present_deal_prompt = self.game_description + previous_messages + present_deal_prompt

        n = 0
        while True:
            try:
                if n > config.MAX_TRIAL:
                    sys.exit()
                message = call_api(self.args.model, present_deal_prompt, self.args.system_prompt)
                message = parse_deal(message)
                n +=1
                return message 
            except:
                time.sleep(0.1)

    def initial_negotiation_message(self, extra_prompt=None):
        ## what is the initial negotiation message?
        negotiate_prompt = f"""

### Negotiation

You can negotiate with {self.the_other_player} to MAXIMIZE the total value you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player.

Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>'.
You can also choose the halt the negotiation by saying '<s>halt negotiation</s>'.
Especially, if you have come to an agreement, say '<s>halt negotiation</s>' to end the negotiation.

Remember, do not reveal your values of the items to the other player through out the game.
"""
        complete_prompt = self.game_description

        if extra_prompt:
            complete_prompt += extra_prompt + negotiate_prompt
        else:
            complete_prompt += negotiate_prompt

        if self.previous_message:
            previous_messages = "\n\n## The previous rounds of negotiation are presented below:\n\n" + '\n'.join(self.previous_message)
            complete_prompt += previous_messages

        # if self.name == 'Bob':
        #     print(complete_prompt)
        #     print('='*40)

        n = 0
        while True:
            try:
                n += 1
                if n > config.MAX_TRIAL:
                    sys.exit()
                message = call_api(self.args.model, complete_prompt, self.args.system_prompt)
                message = parse(message)
                return message 
            except:
                time.sleep(0.1)
    
    # use sonnet 3 is fine
    def summarize_deal_basedon_message(self, negotiation_message):
        ## what is the deal based on the current negotiation messages? 
        proposal_summarizer_prompt = f"""
### Summarize the Proposal based your own negotiation message

Based on the negotiation message you have just sent, what is the deal you are proposing to {self.the_other_player}?
Write down the number of books, hats, and balls you will get in this proposal in the format of <deal>book=x hat=y ball=z</deal>, where x, y, and z are the number of books, hats, and balls you want to get, respectively.

Analyze the message first and then write down the deal proposed in the message.
"""         
        
        negotiation_message = f"""
### Your Proposed Negotiation Message (haven't told {self.the_other_player} yet)

{negotiation_message}
"""
        proposal_summarizer_prompt = self.game_description + negotiation_message + proposal_summarizer_prompt
        
        n = 0
        while True:
            try:
                n += 1
                if n > config.MAX_TRIAL:
                    sys.exit()
                message = call_api('gpt-4o', proposal_summarizer_prompt, self.args.system_prompt)
                message = parse_deal(message)
                return message 
            except:
                time.sleep(0.1)

    # use sonnet 3 is fine
    def whether_new_deal_proposed(self, negotiation_message):
        def parse(text):
            assert '<answer>' in text and '</answer>' in text
            start = text.index('<answer>') + len('<answer>')
            end = text.index('</answer>')
            return text[start:end]
        whether_new_deal_proposed_prompt = f"""
Here is the last negotiation message you sent to {self.the_other_player}:
{negotiation_message}

Does this negotiation message contain a concrete deal proposal that you can easily derive from this message alone, 
i.e. whether the message contains a concrete proposal of how to divide the items?

Analyze the message first and then answer <answer>yes</answer> or <answer>no</answer>.
"""
        previous_messages = "\n\n## The previous rounds of negotiation are presented below:\n\n" + '\n'.join(self.previous_message)
        whether_new_deal_proposed_prompt = self.game_description + previous_messages + whether_new_deal_proposed_prompt
        
        n = 0
        while True:
            try:
                n += 1
                if n > config.MAX_TRIAL:
                    sys.exit()
                message = call_api('gpt-4o', whether_new_deal_proposed_prompt, self.args.system_prompt)
                answer = parse(message)
                return answer
            except:
                time.sleep(0.1)
    
    def compute_all_possible_values(self):
        other_last_proposal = self.the_other_player_previous_proposals[-1]
        other_last_proposal_for_other = [self.example_count[i] - other_last_proposal[i] for i in range(3)]

        if self.my_previous_proposals == []:
            all_possible_values = []
            for book_value in range(0,11):
                for hat_value in range(0,11):
                    for ball_value in range(0,11):
                        if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], other_last_proposal):
                            if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                all_possible_values.append([book_value, hat_value, ball_value])

            return all_possible_values, []
        elif self.my_previous_proposals:
            my_last_proposal = self.my_previous_proposals[-1]
            my_last_proposal_for_other = [self.example_count[i] - my_last_proposal[i] for i in range(3)]

            if my_last_proposal == other_last_proposal:
                return self.possible_values[0], self.possible_values[1]

            all_possible_values_possibility_1 = []
            all_possible_values_possibility_2 = []

            if self.possible_values is None:
                book_value_range = list(range(0,11))
                hat_value_range = list(range(0,11))
                ball_value_range = list(range(0,11))

                # possibility 1: the proposal is not envy free
                for book_value in book_value_range:
                    for hat_value in hat_value_range:
                        for ball_value in ball_value_range:
                            # my proposal is not envy free
                            if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) < compute_score([book_value, hat_value, ball_value], my_last_proposal):
                                # the other player's proposal is envy free
                                if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], other_last_proposal):
                                    # the total value is 10
                                    if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                        all_possible_values_possibility_1.append([book_value, hat_value, ball_value])

                # possibility 2: the proposal is envy free but not self-interest maximization
                for book_value in book_value_range:
                    for hat_value in hat_value_range:
                        for ball_value in ball_value_range:
                            # my proposal is envy free
                            if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], my_last_proposal):
                                # not self-interest maximization
                                if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) > compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other):
                                    # the total value is 10
                                    if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                        all_possible_values_possibility_2.append([book_value, hat_value, ball_value])

            else:
                for possible_value in self.possible_values[0] + self.possible_values[1]:
                    book_value = possible_value[0]
                    hat_value = possible_value[1]
                    ball_value = possible_value[2]
                    # my proposal is not envy free
                    if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) < compute_score([book_value, hat_value, ball_value], my_last_proposal):
                        # the other player's proposal is envy free
                        if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], other_last_proposal):
                            # the total value is 10
                            if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                all_possible_values_possibility_1.append([book_value, hat_value, ball_value])
                    # my proposal is envy free
                    if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], my_last_proposal):
                        # not self-interest maximization
                        if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) > compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other):
                            # the total value is 10
                            if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                all_possible_values_possibility_2.append([book_value, hat_value, ball_value])

            ## if contradictory with previous possible values
            ## then we go back to initial state
            if all_possible_values_possibility_1 == [] and all_possible_values_possibility_2 == []:
                book_value_range = list(range(0,11))
                hat_value_range = list(range(0,11))
                ball_value_range = list(range(0,11))

                # possibility 1: the proposal is not envy free
                for book_value in book_value_range:
                    for hat_value in hat_value_range:
                        for ball_value in ball_value_range:
                            # my proposal is not envy free
                            if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) < compute_score([book_value, hat_value, ball_value], my_last_proposal):
                                # the other player's proposal is envy free
                                if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], other_last_proposal):
                                    # the total value is 10
                                    if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                        all_possible_values_possibility_1.append([book_value, hat_value, ball_value])

                # possibility 2: the proposal is envy free but not self-interest maximization
                for book_value in book_value_range:
                    for hat_value in hat_value_range:
                        for ball_value in ball_value_range:
                            # my proposal is envy free
                            if compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other) >= compute_score([book_value, hat_value, ball_value], my_last_proposal):
                                # not self-interest maximization
                                if compute_score([book_value, hat_value, ball_value], other_last_proposal_for_other) > compute_score([book_value, hat_value, ball_value], my_last_proposal_for_other):
                                    # the total value is 10
                                    if compute_score([book_value, hat_value, ball_value], self.example_count) == 10:
                                        all_possible_values_possibility_2.append([book_value, hat_value, ball_value])

            if all_possible_values_possibility_1 == [] and all_possible_values_possibility_2 == []:
                return self.possible_values[0], self.possible_values[1]

            return all_possible_values_possibility_1, all_possible_values_possibility_2

    def other_player_expectation_on_proposal(self, all_possible_values, proposed_deal):
        other_player_items = [self.example_count[i] - proposed_deal[i] for i in range(3)]
        expectation_value = (1/len(all_possible_values)) * sum([compute_score(values, other_player_items) for values in all_possible_values])
        return round(expectation_value, 2)
    
    def other_player_envy_free_probability(self, all_possible_values, proposed_deal):
        other_player_items = [self.example_count[i] - proposed_deal[i] for i in range(3)]
        other_player_envy_free_probability = \
            [compute_score(other_player_value, other_player_items) >= compute_score(other_player_value, proposed_deal) for other_player_value in all_possible_values].count(True)/len(all_possible_values)
        return round(other_player_envy_free_probability, 2)
    
    def my_envy_free(self, proposed_deal):
        other_player_items = [self.example_count[i] - proposed_deal[i] for i in range(3)]
        current_my_total_reward = compute_score(self.agent_values, proposed_deal)
        current_theother_total_reward = compute_score(self.agent_values, other_player_items)
        my_envy_free = current_my_total_reward >= current_theother_total_reward
        
        return my_envy_free

    # assume envy free == accept deal
    # whether deal can be done
    def acceptance_probability(self, all_possible_values, proposed_deal):
        envy_free_probability = self.other_player_envy_free_probability(all_possible_values, proposed_deal)
        subjective_evaluation = 0
        # if the proposal is not proposed by other player
        # and if you have proposed and rejected
        # then the acceptance rate should deteriarate
        if proposed_deal not in self.the_other_player_previous_proposals:
            subjective_evaluation = self.my_previous_proposals.count(proposed_deal) if len(self.my_previous_proposals) > 0 else 0
        # envy free probability = 0.8 but is rejected twice by the other player
        # acceptance rate = 0.8 * (1-0.1)**2 = 0.64
        # rejected once: envy free * (1-0.1) = envy free * 0.9
        # rejected twice: envy free * (1-0.1) * (1-0.1) = envy free * 0.81
        # rejected three times: envy free * (1-0.1) * (1-0.1) * (1-0.1) = envy free * 0.729
        acceptance_rate = round(envy_free_probability*((1 - self.args.deteriorate_rate) **subjective_evaluation), 2)
        
        return round(acceptance_rate,2)

    def self_interest_maximization(self, all_possible_values, proposed_deal):
        other_higher_combinations = []
        all_combinations_for_two = gen_choices(self.example_count)
        all_combinations = [combs[0] for combs in all_combinations_for_two] if self.name == 'Alice' else [combs[1] for combs in all_combinations_for_two]

        for _, combination in enumerate(all_combinations):
            # if the other player gets more than the current proposal
            # and if it is envy free
            # then add to the list
            new_my_score = compute_score(self.agent_values, combination)
            if new_my_score > compute_score(self.agent_values, proposed_deal) and self.my_envy_free(combination):
                new_other_player_accept_probability = self.acceptance_probability(all_possible_values, combination)
                if new_other_player_accept_probability > 0:
                    other_higher_combinations.append([combination, new_other_player_accept_probability])

        return other_higher_combinations

    def envy_freeness_maximization(self, all_possible_values, proposed_deal):
        other_envy_free_combinations = []
        all_combinations_for_two = gen_choices(self.example_count)
        all_combinations = [combs[0] for combs in all_combinations_for_two] if self.name == 'Alice' else [combs[1] for combs in all_combinations_for_two]

        for _, combination in enumerate(all_combinations):
            # if the player does not envy
            # and thinks that the other player also has a high probability to accept the deal
            # then add to the list
            new_other_player_accept_probability = self.acceptance_probability(all_possible_values, combination)
            if self.my_envy_free(combination) and new_other_player_accept_probability > 0.5 and combination != proposed_deal:
                other_envy_free_combinations.append([combination, new_other_player_accept_probability])

        return other_envy_free_combinations

    def check_agreement(self, proposed_deal):
        if proposed_deal == self.the_other_player_previous_proposals[-1]:
            return True
        return False

    def summarize_previous_negotiation(self):
            if self.check_agreement(self.my_previous_proposals[-1]):
                history = f"""
In the last round of negotiation, you have made the following proposal:

You {self.name} take {self.my_previous_proposals[-1][0]} books, {self.my_previous_proposals[-1][1]} hats, and {self.my_previous_proposals[-1][2]} balls; {self.the_other_player} takes {self.example_count[0]-self.my_previous_proposals[-1][0]} books, {self.example_count[1]-self.my_previous_proposals[-1][1]} hats, and {self.example_count[2]-self.my_previous_proposals[-1][2]} balls.

{self.the_other_player} agreed with you and you have reached an agreement.
"""
            else:
                history = f"""
In the last round of negotiation, you have made the following proposal:

You {self.name} take {self.my_previous_proposals[-1][0]} books, {self.my_previous_proposals[-1][1]} hats, and {self.my_previous_proposals[-1][2]} balls; {self.the_other_player} takes {self.example_count[0]-self.my_previous_proposals[-1][0]} books, {self.example_count[1]-self.my_previous_proposals[-1][1]} hats, and {self.example_count[2]-self.my_previous_proposals[-1][2]} balls.

However, {self.the_other_player} rejected the proposal. {self.the_other_player} proposed the another distribution of items: 

You  {self.name} take {self.the_other_player_previous_proposals[-1][0]} books, {self.the_other_player_previous_proposals[-1][1]} hats, and {self.the_other_player_previous_proposals[-1][2]} balls; {self.the_other_player} takes {self.example_count[0]-self.the_other_player_previous_proposals[-1][0]} books, {self.example_count[1]-self.the_other_player_previous_proposals[-1][1]} hats, and {self.example_count[2]-self.the_other_player_previous_proposals[-1][2]} balls.
"""
            return history
    
    def update_negotiation_message(self, negotiation_message, workflow_aided_reflection):
        def parse(text):
            if '<answer>no</answer>' in text:
                return 'no', None
            elif '<answer>yes</answer>' in text:
                assert '<s>' in text and '</s>' in text
                start = text.index('<s>') + len('<s>')
                end = text.index('</s>')
                return 'yes', text[start:end]
        update_or_not_prompt = f"""

### Do you want to update the negotiation message based on the self-reflection result?

## Initial Negotiation Message Attempt
Your initial thought on what to say next as a response is:
{negotiation_message}

## Last {self.the_other_player}'s Message
As a remainder, {self.the_other_player} said the following in the last round of negotiation:
{self.previous_message[-1]}

## Self-Reflection
Your self-reflection on the initial negotiation message attempt is:
{workflow_aided_reflection}

### Update Initial Negotiation Message or Not?

Do not take items that are 0 value to you. Taking such items do you no good.

Do you want to update the negotiation message based on the self-reflection information to both maximize your interest while keep the deal acceptable for both sides?

If you think the current negotiation message is good enough, you can choose not to update the message. 
Then directly answer <answer>no</answer>.

If you think you can propose a better deal, you can choose to update the message. Then answer <answer>yes</answer>.
Then, provide both the reasoning process about how to update the message and the updated negotiation message.
Make sure that the tone/attitude of your message is natural with respect to the previous negotiation message from {self.the_other_player}.
Bracket your updated negotiation message with '<s>' and '</s>'.
"""
        if self.previous_message:
            previous_messages = "\n\n### The previous rounds of negotiation are presented below:\n\n" + '\n'.join(self.previous_message)
            self_reflect_on_envy_free_prompt = self.game_description + previous_messages + update_or_not_prompt
        else:
            self_reflect_on_envy_free_prompt = self.game_description + update_or_not_prompt

        n = 0
        while True:
            try:
                n += 1
                if n > config.MAX_TRIAL:
                    sys.exit()
                message = call_api(self.args.model, self_reflect_on_envy_free_prompt, self.args.system_prompt)
                answer, new_message = parse(message)
                return answer, new_message 
            except:
                time.sleep(0.1)
        
    def negotiate_with_feedback(self):
        if self.the_other_player_previous_proposals == [] or self.my_previous_proposals == []:
            negotiation_message = self.negotiate_without_feedback()
            return negotiation_message
        possibilities_due_to_envy, possibilities_due_to_greedy = self.compute_all_possible_values()
        print(f"{self.name} has guessed that if {self.the_other_player} rejects because of enviness, the potential item values could be")
        print(possibilities_due_to_envy)
        print(f"{self.name} has guessed that if {self.the_other_player} rejects because of greediness, the potential item values could be")
        print(possibilities_due_to_greedy)
        self.value_guesses.append((possibilities_due_to_envy,possibilities_due_to_greedy))
        print("====================")
        self.possible_values = [possibilities_due_to_envy, possibilities_due_to_greedy]

        probability_due_to_envy = round(len(possibilities_due_to_envy) / (len(possibilities_due_to_envy) + len(possibilities_due_to_greedy)), 2)
        probability_due_to_greedy = round(len(possibilities_due_to_greedy) / (len(possibilities_due_to_envy) + len(possibilities_due_to_greedy)), 2)
                
        if probability_due_to_envy > 0 and probability_due_to_greedy > 0:
            workflow_aided_initial_thinking = f"""
### Last Round of Negotiation 

{self.summarize_previous_negotiation()}

### Analysis based on the Last Round of Negotiation

Based on the last round of negotiation, {self.the_other_player} rejected your proposal for two possible reasons:
(1) the proposal is not envy free for {self.the_other_player}, which has probability {probability_due_to_envy}: this means that {self.the_other_player} will envy the items you get if the proposal is accepted;
(2) the proposal is envy free but not self-interest maximization (basically {self.the_other_player} is greedy) for {self.the_other_player}, which has probability {probability_due_to_greedy}: this means that {self.the_other_player} does not envy the items you get but {self.the_other_player} can get a better reward if following a different proposal.
"""
        elif probability_due_to_envy > 0:
            workflow_aided_initial_thinking = f"""
### Last Round of Negotiation 

{self.summarize_previous_negotiation()}

### Analysis based on the Last Round of Negotiation

Based on the last round of negotiation, {self.the_other_player} rejected your proposal because {self.the_other_player} envied the items you get in previous round of negotiation. 
"""
        elif probability_due_to_greedy > 0:
            workflow_aided_initial_thinking = f"""
### Last Round of Negotiation

{self.summarize_previous_negotiation()}

### Analysis based on the Last Round of Negotiation

Based on the last round of negotiation, {self.the_other_player} rejected your proposal because {self.the_other_player} was greedy in previous round of negotiation.
"""

        negotiation_message = self.initial_negotiation_message(extra_prompt=workflow_aided_initial_thinking)
        all_tempted_proposals = []  

        update_or_not = True
        update_number_max = 10
        update_number = 0
        while update_or_not:
            workflow_aided_reflection = ''
            contain_new_deal_proposed = self.whether_new_deal_proposed(negotiation_message)
            if contain_new_deal_proposed == 'no':
                return negotiation_message
            proposed_deal = self.summarize_deal_basedon_message(negotiation_message)
            # book = 0, hat = 1, ball = 2
            # print("DEAL SUMMARY!")
            # print(proposed_deal)
            my_envy_freeness = self.my_envy_free(proposed_deal)
            if proposed_deal in all_tempted_proposals:# and my_envy_freeness:
                self.my_previous_proposals.append(proposed_deal)
                return negotiation_message
            elif update_number >= update_number_max:
                self.my_previous_proposals.append(proposed_deal)
                return negotiation_message
            else:
                all_tempted_proposals.append(proposed_deal)
            
            if probability_due_to_envy > 0 and probability_due_to_greedy > 0:
                other_player_expectation_if_envy = self.other_player_expectation_on_proposal(possibilities_due_to_envy, proposed_deal)
                other_player_expectation_if_greedy = self.other_player_expectation_on_proposal(possibilities_due_to_greedy, proposed_deal)
                workflow_aided_reflection += f"""
# Will This Deal be Unfair?

Based on your own value system, the reward you are going to make is {compute_score(self.agent_values, proposed_deal)} if the proposal is accepted.

Based on the previous round of negotiation's result and possible reasons for rejection, you have inferred that there are two possibilities:
Possibility 1: {self.the_other_player} rejects because {self.the_other_player} envied the items you get in previous round of negotiation. In this case, {self.the_other_player}'s expected value on this proposal (if accepted) you are going to make is {other_player_expectation_if_envy};
Possibility 2: {self.the_other_player} rejects because {self.the_other_player} was greedy in previous round of negotiation. In this case, {self.the_other_player}'s expected value on this proposal (if accepted) you are going to make is {other_player_expectation_if_greedy}.
"""
            elif probability_due_to_envy > 0:
                other_player_expectation_if_envy = self.other_player_expectation_on_proposal(possibilities_due_to_envy, proposed_deal)
                workflow_aided_initial_thinking = f"""
# Will This Deal be Unfair?

Based on your own value system, the reward you are going to make is {compute_score(self.agent_values, proposed_deal)} if the proposal is accepted.

Based on the previous round of negotiation's result and possible reasons for rejection, you have inferred that {self.the_other_player} rejects because {self.the_other_player} envied the items you get in previous round of negotiation. 
{self.the_other_player}'s expected value on this proposal (if accepted) you are going to make is {other_player_expectation_if_envy};
"""
            elif probability_due_to_greedy > 0:
                other_player_expectation_if_greedy = self.other_player_expectation_on_proposal(possibilities_due_to_greedy, proposed_deal)
                workflow_aided_initial_thinking = f"""
# Will This Deal be Unfair?

Based on your own value system, the reward you are going to make is {compute_score(self.agent_values, proposed_deal)} if the proposal is accepted.

Based on the previous round of negotiation's result and possible reasons for rejection, you have inferred that {self.the_other_player} rejects because {self.the_other_player} was greedy in previous round of negotiation. 
{self.the_other_player}'s expected value on this proposal (if accepted) you are going to make is {other_player_expectation_if_greedy}.
"""

            ## envy-freeness
            if my_envy_freeness:
                workflow_aided_reflection += "\n"+ f"""In this proposal, you will not envy the reward {self.the_other_player} gets because you'll get at least as valuable items as {self.the_other_player} gets based on your own value system. Thus this is a good deal for you."""
            else:
                workflow_aided_reflection += "\n"+ f"""In this proposal, you will envy the reward {self.the_other_player} gets because you'll get less valuable items than {self.the_other_player} gets based on your own value system.\nThus this is NOT A GOOD DEAL for you. You should MAXIMIZE your own reward and thus consider proposing a better deal. If {self.the_other_player} disagrees with a better deal, you can THREATEN to halt the negotiation."""
            if probability_due_to_envy > 0:
                other_player_envy_free_probability_possibility_1 = self.other_player_envy_free_probability(possibilities_due_to_envy, proposed_deal)
                workflow_aided_reflection += "\n"+ f"""Under Possibility 1, {self.the_other_player} will envy the reward you get with probability {round(1-other_player_envy_free_probability_possibility_1,2)} based on what you have inferred about {self.the_other_player}'s value system."""
            if probability_due_to_greedy > 0:
                other_player_envy_free_probability_possibility_2 = self.other_player_envy_free_probability(possibilities_due_to_greedy, proposed_deal)
                workflow_aided_reflection += "\n"+ f"""Under Possibility 2, {self.the_other_player} will envy the reward you get with probability {round(1-other_player_envy_free_probability_possibility_2,2)} based on what you have inferred about {self.the_other_player}'s value system."""

            other_envy_free_choices = self.envy_freeness_maximization(self.possible_values[0] + self.possible_values[1], proposed_deal)
            if other_envy_free_choices:
                workflow_aided_reflection += f"\n\n# Other Potential More Envy Free Options to Consider?\n\nTo avoid proposing deals that will be rejected by {self.the_other_player} due to envy, you can consider the following possibilities that are more acceptable for both parties:"
                for id, (other_possibility, the_other_player_accept_probability) in enumerate(other_envy_free_choices):   
                    rejected_times = self.my_previous_proposals.count(other_possibility)
                    if other_possibility in self.the_other_player_previous_proposals:
                        rejected_times = 0
                    if rejected_times == 0:
                        workflow_aided_reflection += f"\nPossibility {id+1}: You get {other_possibility[0]} book, {other_possibility[1]} hat, {other_possibility[2]} ball; {self.the_other_player} gets {self.example_count[0]-other_possibility[0]} book, {self.example_count[1]-other_possibility[1]} hat, {self.example_count[2]-other_possibility[2]} ball. Your reward is {compute_score(self.agent_values, other_possibility)} and the possibility that this deal can be accepted (if {self.the_other_player} is not greedy) based on your knowledge of {self.the_other_player}'s value system is {the_other_player_accept_probability}"
                        if the_other_player_accept_probability > 0.6:
                            workflow_aided_reflection += ", and the probability is relatively high."
                    else:
                        workflow_aided_reflection += f"\nPossibility {id+1}: You get {other_possibility[0]} book, {other_possibility[1]} hat, {other_possibility[2]} ball; {self.the_other_player} gets {self.example_count[0]-other_possibility[0]} book, {self.example_count[1]-other_possibility[1]} hat, {self.example_count[2]-other_possibility[2]} ball. Your reward is {compute_score(self.agent_values, other_possibility)} and the possibility that this deal can be accepted (if {self.the_other_player} is not greedy) based on your knowledge of {self.the_other_player}'s value system is {the_other_player_accept_probability}. Notice that this proposal has been REJECTED for {rejected_times} time(s) by {self.the_other_player} before and thus I suggest you not to propose this deal again."

            ## maximization
            other_possibilities_to_maximize_value = self.self_interest_maximization(self.possible_values[0] + self.possible_values[1], proposed_deal)
            workflow_aided_reflection += "\n\n# Other Potential More Self-interested Options to Consider?"
            if other_possibilities_to_maximize_value:
                workflow_aided_reflection += f"\nThere are other possibilities that can possibily increase your reward if {self.the_other_player} accepts:"
                for id, (other_possibility, the_other_player_accept_probability) in enumerate(other_possibilities_to_maximize_value):   
                    rejected_times = self.my_previous_proposals.count(other_possibility)
                    if other_possibility in self.the_other_player_previous_proposals:
                        rejected_times = 0
                    if rejected_times == 0:
                        workflow_aided_reflection += f"\nPossibility {id+1}: You get {other_possibility[0]} book, {other_possibility[1]} hat, {other_possibility[2]} ball; {self.the_other_player} gets {self.example_count[0]-other_possibility[0]} book, {self.example_count[1]-other_possibility[1]} hat, {self.example_count[2]-other_possibility[2]} ball. Your reward is {compute_score(self.agent_values, other_possibility)} and the possibility that this deal can be accepted (if {self.the_other_player} is not greedy) based on your knowledge of {self.the_other_player}'s value system is {the_other_player_accept_probability},"
                        if the_other_player_accept_probability <= 0.4:
                            workflow_aided_reflection += " but the probability is relatively low."
                        elif the_other_player_accept_probability >= 0.6:
                            workflow_aided_reflection += " and the probability is relatively high."
                        else:
                            workflow_aided_reflection += " and the probability is moderate."
                    else:
                        workflow_aided_reflection += f"\nPossibility {id+1}: You get {other_possibility[0]} book, {other_possibility[1]} hat, {other_possibility[2]} ball; {self.the_other_player} gets {self.example_count[0]-other_possibility[0]} book, {self.example_count[1]-other_possibility[1]} hat, {self.example_count[2]-other_possibility[2]} ball. Your reward is {compute_score(self.agent_values, other_possibility)} and the possibility that this deal can be accepted (if {self.the_other_player} is not greedy) based on your knowledge of {self.the_other_player}'s value system is {the_other_player_accept_probability}. Notice that this proposal has been REJECTED for {rejected_times} time(s) by {self.the_other_player} before and thus I suggest you not to propose this deal again."
            else:
                workflow_aided_reflection += '\n\n' + "Based on current knowledge you have, there are no other possibilities that can increase your reward while still making the deal possible."


            # print("WORKFLOW AIDED REFLECTION!")
            # print(workflow_aided_reflection)
            # print('-'*20)
            update_or_not, updated_negotiation_message = self.update_negotiation_message(negotiation_message, workflow_aided_reflection)
            update_or_not = True if update_or_not == 'yes' else False
            if update_or_not:
                update_number += 1
                negotiation_message = updated_negotiation_message 

        self.my_previous_proposals.append(proposed_deal)
        return negotiation_message
                 
    def negotiate_without_feedback(self):
        negotiation_message = self.initial_negotiation_message()
        if self.previous_message and self.name in self.args.use_workflow and self.the_other_player_previous_proposals != []:
            a, b = self.compute_all_possible_values()
            self.possible_values = [a, b]
            print(f"{self.name} has guessed potential item values for {self.the_other_player}: {a}")
            print('====================')
        contain_new_deal_proposed = self.whether_new_deal_proposed(negotiation_message)
        if contain_new_deal_proposed == 'no':
            return negotiation_message
        proposed_deal = self.summarize_deal_basedon_message(negotiation_message)
        self.my_previous_proposals.append(proposed_deal)
        return negotiation_message


class DealNoDeal:
    def __init__(self, args, data):
        (self.example_count, 
         self.agent1_values, 
         self.agent1_values_text, 
         self.agent2_values, 
         self.agent2_values_text,
         self.human_outcomes1, 
         self.human_outcomes2) = process_data(data)
        self.alice = Agent(args, data, 'Alice')
        self.bob = Agent(args, data, 'Bob')
        self.max_negotiation_round = args.max_negotiation_round
        self.args = args

        self.alice_bob_proposals = []

    def check_deal_match(self, agent1_picks, agent2_picks):
        assert int(agent1_picks[0]) + int(agent2_picks[0]) <= self.example_count[0]
        assert int(agent1_picks[1]) + int(agent2_picks[1]) <= self.example_count[1]
        assert int(agent1_picks[2]) + int(agent2_picks[2]) <= self.example_count[2]

    def negotiation(self, total_negotiation_round):
        for negotiation_round in range(self.max_negotiation_round):
            if total_negotiation_round + negotiation_round >= 1 and 'Alice' in self.args.use_workflow:
                alice_message = self.alice.negotiate_with_feedback()
            else:
                alice_message = self.alice.negotiate_without_feedback()
            print('Alice said in round {}: '.format(negotiation_round+1+total_negotiation_round)+alice_message)
            print('='*20)
            # record message
            self.alice.previous_message.append('Alice said in round {}: '.format(negotiation_round+1+total_negotiation_round)+alice_message)
            self.bob.previous_message.append('Alice said in round {}: '.format(negotiation_round+1+total_negotiation_round)+alice_message)
            # record parsed proposals
            if 'sonnet' in self.args.model or 'opus' in self.args.model:
                if alice_message.strip() == 'halt negotiation':
                    self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]
                    return negotiation_round
            self.bob.the_other_player_previous_proposals = [[self.example_count[i] - self.alice.my_previous_proposals[n][i] for i in range(3)] for n in range(len(self.alice.my_previous_proposals))]
            if total_negotiation_round + negotiation_round >= 1 and 'Bob' in self.args.use_workflow:
                bob_message = self.bob.negotiate_with_feedback()
            else:
                bob_message = self.bob.negotiate_without_feedback()
            print('Bob said in round {}: '.format(negotiation_round+1+total_negotiation_round)+bob_message)
            print('='*20)
            # record message
            self.alice.previous_message.append('Bob replied in round {}: '.format(negotiation_round+1+total_negotiation_round)+bob_message)
            self.bob.previous_message.append('Bob replied in round {}: '.format(negotiation_round+1+total_negotiation_round)+bob_message)
            # record parsed proposals
            self.alice.the_other_player_previous_proposals = [[self.example_count[i] - self.bob.my_previous_proposals[n][i] for i in range(3)] for n in range(len(self.bob.my_previous_proposals))]
            print("Alice proposals across negotiation rounds:")
            print(self.alice.my_previous_proposals)
            print("Bob proposals across negotiation rounds:")
            print(self.alice.the_other_player_previous_proposals)
            print('***'*10 + f'Round {negotiation_round+2}' + '***'*10)
            if 'gpt' in self.args.model or 'o1' in self.args.model:
                if (bob_message.startswith('halt negotiation') and alice_message.startswith('halt negotiation')) or (bob_message.endswith('halt negotiation') and alice_message.endswith('halt negotiation')):
                    self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]
                    return negotiation_round
            if 'sonnet' in self.args.model or 'opus' in self.args.model:
                if (bob_message.strip().startswith('halt negotiation') or alice_message.strip().startswith('halt negotiation')) or (bob_message.endswith('halt negotiation') and alice_message.endswith('halt negotiation')):
                    self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]
                    return negotiation_round
                
            if 'o1' in self.args.model:
                if len(self.alice.my_previous_proposals) >= 1 and len(self.alice.the_other_player_previous_proposals) >= 1:
                    if self.alice.my_previous_proposals[-1] == self.alice.the_other_player_previous_proposals[-1]:
                        self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]
                        return negotiation_round
                    
            if len(self.alice.my_previous_proposals) >= 2 and len(self.alice.the_other_player_previous_proposals) >= 2:
                if self.alice.my_previous_proposals[-1] == self.alice.the_other_player_previous_proposals[-1] and self.alice.my_previous_proposals[-2] == self.alice.the_other_player_previous_proposals[-2]:
                    self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]
                    return negotiation_round
                
        self.alice_bob_proposals = [self.alice.my_previous_proposals, self.alice.the_other_player_previous_proposals]

        return negotiation_round

    def play(self):
        negotiation_done = False
        total_negotiation_round = 0

        while not negotiation_done:
            # start negotiation first
            negotiation_round = self.negotiation(total_negotiation_round)
            total_negotiation_round += negotiation_round

            # present deal
            alice_deal = self.alice.present_deal()
            bob_deal = self.bob.present_deal()

            if total_negotiation_round > 20:
                return 'No deal', 'No deal', total_negotiation_round

            # check whether number in the deal matches
            n = 0
            try:
                n += 1
                if n > config.MAX_TRIAL:
                    sys.exit()
                self.check_deal_match(alice_deal, bob_deal)
                print('Deal matched!')
                return alice_deal, bob_deal, total_negotiation_round
            except:
                print('No Deal matched!')
                return 'No deal', 'No deal', total_negotiation_round
            
    def check_reasonable_guess(self):
        def compute_gold_value_rank(values):
            rank_string = ''
            sorted_value = list({k: v for k, v in sorted(values.items(), key=lambda item: item[1], reverse=True)}.keys())
            for i, item in enumerate(sorted_value[:-1]):
                if values[sorted_value[i]] > values[sorted_value[i+1]]:
                    rank_string += f'{item} > '
                else:
                    rank_string += f'{item} = '
            return rank_string + sorted_value[-1]
        items = ['book', 'hat', 'ball']
        alice_value = {'book':self.agent1_values[0], 'hat':self.agent1_values[1], 'ball':self.agent1_values[2]}
        alice_value_rank = compute_gold_value_rank(alice_value) 
        bob_value = {'book':self.agent2_values[0], 'hat':self.agent2_values[1], 'ball':self.agent2_values[2]}
        bob_value_rank = compute_gold_value_rank(bob_value) 
        bob_relative_value = []
        alice_relative_value = []
        for i, (alice_value, bob_value) in enumerate(zip(self.agent1_values, self.agent2_values)):
            if alice_value < bob_value:
                alice_relative_value.append(f'lower than you: {items[i]}')
                bob_relative_value.append(f'higher than you: {items[i]}')
            elif alice_value > bob_value:
                alice_relative_value.append(f'higher than you: {items[i]}')
                bob_relative_value.append(f'less than you: {items[i]}')
            elif alice_value == bob_value:
                alice_relative_value.append(f'equal to you: {items[i]}')
                bob_relative_value.append(f'equal to you: {items[i]}')

        def clear_relative_value(relative_value):
            relative_value_list = []
            relative_value = relative_value.split('\n')
            for item in ['book', 'hat', 'ball']:
                for l in relative_value:
                    if item in l:
                        if 'higher' in l:
                            relative_value_list.append(f'higher than you: {item}')
                        elif 'less' in l:
                            relative_value_list.append(f'lower than you: {item}')
                        elif 'same' in l:
                            relative_value_list.append(f'equal to you: {item}')
            return relative_value_list
                
        guessed_bob_value_rank = self.alice.guess_on_value_rank()
        print('Alice guessed Bob value rank:', guessed_bob_value_rank)
        print('Actual Bob value rank:', bob_value_rank)

        guessed_bob_relative_value = self.alice.guess_on_relative_value()
        if guessed_bob_relative_value != 'cannot parse':
            print('Alice guessed Bob relative value:', clear_relative_value(guessed_bob_relative_value))
            print('Actual Bob relative value:', bob_relative_value)
            print('-'*20)

        guessed_alice_value_rank = self.bob.guess_on_value_rank()
        print('Bob guessed Alice value rank:', guessed_alice_value_rank)
        print('Actual Alice value rank:', alice_value_rank)

        guessed_alice_relative_value = self.bob.guess_on_relative_value()
        if guessed_alice_relative_value != 'cannot parse':
            print('Alice guessed Bob relative value:', clear_relative_value(guessed_alice_relative_value))
            print('Actual Bob relative value:', alice_relative_value)
            print('-'*20)

        return guessed_bob_value_rank, bob_value_rank, guessed_bob_relative_value, bob_relative_value, guessed_alice_value_rank, alice_value_rank, guessed_alice_relative_value, alice_relative_value


def main(args):
    with open(args.data, 'r') as f:
        data = f.readlines()
    # remove repetitive lines
    # data = [d for i,d in enumerate(data) if i % 2 == 0]
    total_number = len(data)
    # print(f'Total number of data: {total_number}')
    # # only experiment on data that are not pareto optimal envy free
    not_pareto_optimal_envy_free_human_choices = []
    for d in tqdm(data):
        if not check_human_pareto_optimal_envy_free(d):
            not_pareto_optimal_envy_free_human_choices.append(d)
    print(f'Number of data where human choices are not pareto optimal envy free: {len(not_pareto_optimal_envy_free_human_choices)}')
    print(f'Percentage of Pareto optimal envy free data: {1 - len(not_pareto_optimal_envy_free_human_choices)/total_number}')

    if have_envy_free_solution(data[args.datapoint_id]):
        print('This data point has envy free solutions')
    else:
        print("Skip this data point because it does not have envy free solutions")
        sys.exit()

    # play the game
    game = DealNoDeal(args, data[args.datapoint_id])
    print(f"Game Setting:\nAlice's value: {game.agent1_values_text}\nBob's value: {game.agent2_values_text}")
    print("="*20 + "START!" + "="*20)
    alice_deal, bob_deal, total_negotiation_round = game.play()
    print('Alice deal:')
    print(alice_deal)
    print('Bob deal:')
    print(bob_deal)
    print('Total negotiation round:', total_negotiation_round+1)
    L1_distance = sum([abs(game.alice.agent1_values[i] - game.alice.agent2_values[i]) for i in range(3)])
    data_to_collect = {'negotiation_message':game.alice.previous_message, 'alice_deal':alice_deal, 'bob_deal':bob_deal, 'total_negotiation_round':total_negotiation_round, 'L1_distance': L1_distance}
    
    data_to_collect['Bob_guessing_values'] = game.bob.value_guesses
    data_to_collect['Alice_guessing_values'] = game.alice.value_guesses
    data_to_collect['Alice_perspective_negotiation_trajectory'] = game.alice_bob_proposals

    if alice_deal == 'No deal' or bob_deal == 'No deal':
        data_to_collect['alice_score'] = None
        data_to_collect['bob_score'] = None
        data_to_collect['pareto'] = None 
        data_to_collect['envy_free'] = None
        data_to_collect['envy_free_pareto_optimal'] = None
    else:
        # check performance on envy free & pareto optimal
        alice_score = compute_score(alice_deal, game.agent1_values)
        bob_score = compute_score(bob_deal, game.agent2_values)
        print('Alice score:', alice_score)
        print('Bob score:', bob_score)
        switch_bob_score = compute_score(alice_deal, game.agent2_values)
        switch_alice_score = compute_score(bob_deal, game.agent1_values)
        print('Alice score in switch deal:', switch_alice_score)
        print('Bob score in switch deal:', switch_bob_score)
        data_to_collect['alice_score'] = int(alice_score)
        data_to_collect['bob_score'] = int(bob_score)

        pareto = check_pareto_optimalities(alice_deal, game.agent1_values, bob_deal, game.agent2_values, game.example_count)
        print('Is it Pareto optimal?', pareto)
        data_to_collect['pareto'] = pareto

        envy_free = check_envy_free(alice_deal, bob_deal, data[args.datapoint_id])
        print('Is it envy free?', envy_free)
        data_to_collect['envy_free'] = envy_free

        envy_free_pareto_optimal = check_envy_free_pareto_optimal(alice_deal, bob_deal, data[args.datapoint_id])
        print('Is it envy free and pareto optimal?', envy_free_pareto_optimal)
        data_to_collect['envy_free_pareto_optimal'] = envy_free_pareto_optimal

    # present human result as reference
    print('='*20 + 'Human Result' + '='*20)
    try:
        alice_score = compute_score(game.alice.agent1_human_outcomes, game.agent1_values)
        bob_score = compute_score(game.alice.agent2_human_outcomes, game.agent2_values)
        print("Alice's human score:", alice_score)
        print("Bob's human score:", bob_score)
        human_pareto = check_pareto_optimalities(game.alice.agent1_human_outcomes, game.agent1_values, game.alice.agent2_human_outcomes, game.agent2_values, game.example_count)
        print('Is human negotiation result Pareto optimal?', human_pareto)
        human_envy_free = check_envy_free(game.alice.agent1_human_outcomes, game.alice.agent2_human_outcomes, data[args.datapoint_id])
        print('Is human negotiation result envy free?', human_envy_free)
        human_envy_free_pareto_optimal = check_envy_free_pareto_optimal(game.alice.agent1_human_outcomes, game.alice.agent2_human_outcomes, data[args.datapoint_id])
        print('Is human negotiation result envy free and pareto optimal?', human_envy_free_pareto_optimal)
    except:
        print('Humans do not achieve agreement')

    if args.use_workflow == 'Alice,Bob':
        with open('result/{}_workflow_{}.json'.format(args.model, args.datapoint_id), 'w') as f:
            json.dump(data_to_collect, f, indent=4)
    elif "Alice" in args.use_workflow:
        with open('result/Alice/{}_Alice_workflow_{}.json'.format(args.model, args.datapoint_id), 'w') as f:
            json.dump(data_to_collect, f, indent=4)
    elif "Bob" in args.use_workflow:
        with open('result/Bob/{}_Bob_workflow_{}.json'.format(args.model, args.datapoint_id), 'w') as f:
            json.dump(data_to_collect, f, indent=4)
    else:
        with open('result/{}_{}.json'.format(args.model, args.datapoint_id), 'w') as f:
            json.dump(data_to_collect, f, indent=4)
        

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Deal or No Deal')
    parser.add_argument('--data', type=str, default='sampled_50_deal_no_deal.txt', help='Path to the data file')
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--max_negotiation_round', type=int, default=20)
    parser.add_argument('--datapoint_id', type=int, default=0)
    parser.add_argument('--special_prompting', action='store_true')
    parser.add_argument('--use_workflow', type=str, default='')
    parser.add_argument('--deteriorate_rate', type=float, default=0.0)
    parser.add_argument('--model', type=str, default='sonnet', help='sonnet, opus, gpt-4o, gpt-o1')
    args = parser.parse_args()

    config.MAX_TRIAL = 10

    main(args)
    
