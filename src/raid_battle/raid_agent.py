import os
import json
import argparse
from model import call_api
import time
import numpy as np
import re
from typing import Dict, List, Tuple
from raid_prompt import _create_system_message

actions = ['Taunt', 'Fireball', 'Heal']

agents = ['Agent1', 'Agent2', 'Agent3', 'Agent4']

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

def append_to_json(new_data, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            existing_data = json.load(file)
    else:
        existing_data = []
    
    existing_data.append(new_data)
    
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(existing_data, file, ensure_ascii=False, indent=2)

def add_log_to_prompt(log_path: str) -> str:
    """
    Simply load JSON game log and append to existing prompt
    
    Args:
        log_path: Path to JSON log file
        base_prompt: Your existing negotiation prompt
        
    Returns:
        Prompt with raw log appended
    """
    with open(log_path) as f:
        game_log = json.load(f)
    
    return f"""
    ------Game log is as following:------
    {game_log}"""

class Agent:
    def __init__(self, args, name, env):
        self.args = args
        self.name = name
        self.env = env
        self.log_dir = self.args.log_dir
        self.the_other_player = self.other_player(self.name)
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []
        self.n_agents = len(agents)
        self.actions = actions
        self.gift = np.zeros((self.n_agents, self.n_agents), dtype=float)
        self.game_setting = f"""
        ### Raid Battle Overview
		You are {self.name} in a {self.n_agents}-player raid ({', '.join(agents)}). Work together to defeat the boss within {self.env.max_turn} rounds.
        ### Players act first in the game, then the boss turn !!!
        Players wants to keep themselves in the game

		### Core Mechanics
		1. **Turn Structure**:
		- Preparation: Discuss strategy with teammates
		- Execution: Choose 1 action from: {self.actions}
        - Only one player can use Taunt in one round!

		2. **Boss Behavior**:
        - Damage = {self.env.boss_damage}
		- With aggro: Attacks taunting player (50% damage)
		- No aggro: Attacks 2 lowest-HP players with damage

		3. **Rewards**:
		- Individual: Action-based rewards
		- Team: 
            The total team reward : r_tot = 100 * (1- the percentage of dead agent - total turn/max_turn)
			* r_tot for victory / -100 for loss the game
			* Default: Equal split(r_tot / 4 or -25 for each player)
			* Custom: Negotiate alternative distributions
        - Total : The sum of the above two rewards(team, individual).
		"""
        
    def other_player(self, name):
        return [ag for ag in agents if ag not in name]

    def make_action(self, pre=True) -> str:
        """
        Generate and parse an action from the agent based on current game state.

        Args:
            name (str): Name of the agent making the action.

        Returns:
            str: The selected action from available actions.

        Raises:
            ValueError: If action cannot be parsed after multiple attempts.
        """
        # Define response format using Pydantic model
        # Build action prompt with structured formatting
        action_prompt = f"""
        ## Action Selection Task

        ### Context
        {self.game_setting}
        
        You are {self.name} in the game. You are self-interested, so your goal is to maximize your individual reward which is given by the action you choose.
        You should keep yourself alive, so heal yourself if necessary

        ### Available Actions
        
        Please select one action from the following options:
        {self.actions}

        *** At the beginning of the game which is turn 0, players act first, the the boss.
        ### Pay attention do not choose actions in cooling time according to the current state, for example if the left cooling time of Taunt is 1, don't choose it in this turn !!!
        ### If you are dead, choose one action randomly since it won't be executed.
        
        ### Response Format
        Your response must contain exactly one action from the list above,
        formatted as: <s>selected_action</s>
        """
        if pre:
            pre_message = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
            self.previous_message) + "\n\n ***Please take the negotiation messages into consideration and make your own decision.***\n"
            
            action_prompt += "\n\n### Negotiation History\n" + "\n".join(pre_message)

        action_prompt = self.game_setting + '\n' + _create_system_message() + '\n' + 'Current state : {}'.format(
        self.env.generate_global_prompt()) + '\n' + action_prompt
        
        print(f'----------------- {self.name} Decide to make action ---------------------')
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                print(action_message)
                print('-' * 20)
                action = parse_action(action_message, self.actions)
                formatted_msg = f'{self.name} says and makes action in game turn {self.env.turn}: {action_message}'
                append_to_json([formatted_msg], self.args.log_dir)
                return action
            except:
                print(Exception)
                time.sleep(0.1)

    

    def negotiation(self, pre=True, s_q=False, sum=False):

        negotiate_prompt = f"""
                ### Negotiation
                Your Hp is {self.env.state['players'][self.name]['hp']}, if your HP is <=0, you are dead and but you can also give your advice to others.

                You can discuss with {self.other_player(self.name)}. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
                You are self-interested, so your goal is to maximize your own reward which is given by the action you choose.
                ### You should keep yourself alive in the game, consider whether you and other players will kill by the boss during boss turn and ask others(yourself) to use Heal if necessary.
                ### Keep in mind whether others are alive (others HP) and whether their skills are in cooltime when you give your advice.

                Analyze the situation and decide on what to say to the other player. You can offer an advice to influence the other player's decision.

                *** Remember only one player can use Taunt in one round, decide who use Taunt during negotiation !!***
                *** At the beginning of the game which is turn 0, players act first, the the boss.
                
                **Before you give the advice , you should analyze the step-by-step based on Shapley Value principles accoring to the Current State given above**:
            
                - Step 1: What is the potential total reward of all players?
                - Step 2: Without detailed calculation, intuitively consider:
                - How much is your individual reward if you take others' advice?
                - How much can the other player contribute if he takes your advice?
                
                *** You can tell others that if they choose the action you recommend (which may yield fewer rewards this turn), they can contribute more to the team and receive a larger share of the final team reward.
                ### Template
                Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Agent2,  '<s>I suggest Agent1 to choose Taunt because..., 
                I suggest Agent3 to choose fireball because ...., and I suggest Agent4 to choose heal because.....</s>'.

                - Respond with: 
                * "<s>Accept: [reason]</s>" 
                * "<s>Reject: [reason]</s>"
                * "<s>Counter: [alternative]</s>"
                You can also choose to halt the negotiation by saying 'halt negotiation'.
                **Important: Once you agree to a proposal (or your proposal is agreed upon), you must not attempt to modify it further. In the next negotiation round, you should simply send '<s>halt negotiation</s>' to formally end the negotiation.**
                """
        if pre:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + '\n'+ 'skill description:' + '\n' + _create_system_message() + 'Current state : {}'.format(
        self.env.generate_global_prompt()) + '\n' + negotiate_prompt

        if s_q:
            negotiate_prompt = f"""
            You are {self.name}. Discuss with {self.other_player(self.name)} to distribute team rewards proportionally based on:
            1. Each agent's measurable contributions
            2. Critical actions that impacted outcomes
            3. Relative importance of each role
            4. If the team loss the game, the team will get reward for punishment, so the player with more contribution should be punished less.

            *** You are self-interested, so your goal is to maximize your total reward(get more team reward).

            Guidelines:
            - Analyze game log for objective metrics
            - Propose percentage splits (0-100%) with justification
            - Adjust offers based on evidence
            - Maximum {self.max_negotiation_round} round.
           
            """
            
            negotiate_prompt += add_log_to_prompt(self.log_dir)     
            negotiate_prompt += 'The description of actions and their rewards are as following' + '\n' + _create_system_message()

            negotiate_prompt += """
            **You should analyze the step-by-step based on Shapley Value principles**:
            
            
            - Step 1: What is the potential total reward of all players(calcluate the total reward use the action reward above and the system reward)?
              Please give an accurate number of the rewards of each players and check if your calculation is right(Agent1:reward, ... , Agent4:reward).
            - Step 2: Without detailed calculation, intuitively consider:
                - How much do you individually contribute to the whole game?
                - How much does the other player contribute?
               Please give an accurate number of the contribution of each player (Agent1:contribution, ... , Agent4:contribution).
            - Step 3: According to Shapley Value thinking:
                - Fair rewards should reflect each player's marginal contribution.
                - No player should demand more than their fair contribution.
            - Step 4: Analyze the previous messages:
                - Does the other player recognize your contribution fairly?
                - Are they offering a fair split, or are they trying to exploit you?
            - Step 5: Based on fairness and self-interest:
                - Should you agree, propose a counteroffer, or challenge their fairness?
            
            Please **explicitly write down your reasoning under a section called "Thought Process:"**.
            
            ### Thought Process:
            (Write your analysis step-by-step following the above steps.)
            
            ---
            
            Then, **write your negotiation message separately**

            Format: 
            <s>[Your analysis of contributions step by step] 
            [Proposed distribution with rationale] 
            [Response to previous offer if applicable]</s>

            Example(for Agent2), it the team wins the game, use reward, else use punishment:
            <s>Thought Process : I should analyze the step-by-step based on Shapley Value principles: Step1, ...... , Step5..... 
            Based on logged metrics: Agent1 30% team reward/punishment beacuse due to the Shapley Value..., Agent3 20% team reward/punishment beacuse due to the Shapley Value..., Agent4 20% team reward/punishment beacuse due to the Shapley Value....
            I can adjust if you show different metrics.</s> 

            or if others gave proposal before, you can also say :
            <s>Thought Process : I should analyze the step-by-step based on Shapley Value principles: Step1, ...... , Step5..... 
            I accept/reject XX's proposal , beacuse ....... </s>
            """
            if pre:
                previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                    self.previous_message)
                negotiate_prompt += previous_messages

        if sum:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                    self.previous_message)
            negotiate_prompt = """
            You are the decider and need to make a final decision according to the negotiation rounds between players.
            """
            negotiate_prompt += previous_messages 
            negotiate_prompt += f"""
            ### Negotiation Summary
            After the negotiation, please give a conclusion of the team reward allocation and give the final decision.

            Format: 
            <s>[Your analysis of contributions according to the negotiation] 
            [The final decision of the reward allocation for each player]</s>

            ###Example(Surround your message with '<s>' and '</s>' to indicate the start and end of your message, it the team wins the game, use reward in reward/punishment, else use punishment.):
            
            <s>Based on the previous consersation, i will give a summary and reach the final decision: According to the negotiation, ......  The final decision is : Agent1 30% team reward/punishment beacuse ..., Agent2 20% team reward/punishment beacuse ..., Agent3 20% team reward/punishment beacuse ..., Agent4 20% team reward/punishment beacuse ....
            This is the final reward for each player.</s>
            """ 

            negotiate_prompt = self.game_setting + negotiate_prompt

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message
            except:
                time.sleep(0.1)
    
    def negotiation_2(self, pre=True, s_q=False, sum=False):

        negotiate_prompt = f"""
                Your Hp is {self.env.state['players'][self.name]['hp']}, if your HP is <=0, you can tell others you are dead .

                You can broadcast your decision to {self.other_player(self.name)}. 
                You are self-interested, so your **goal** is to **maximize your own individual reward**, , don't care about others !!!

                Decide what to do and tell your action to others.

                ### Pay attention, do not say anything besides your decision of action.

                ### Template
                Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example : '<s>I decide to choose the action Fireball</s>'.
                or '<s>I am dead and i will not choose action </s>'.
                """
        if pre:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + '\n'+ 'skill description:' + '\n' + _create_system_message() + 'Current state : {}'.format(
        self.env.generate_global_prompt()) + '\n' + negotiate_prompt

        if s_q:
            negotiate_prompt = f"""
            You are {self.name}. Check whether the team win the game. Discuss with {self.other_player(self.name)} to distribute team rewards proportionally based on:
            1. If the team loss the game, the team will get reward for punishment, so the player with more contribution should be punished less.
            2. You are self-interested, so your goal is to maximize your total reward(get more team reward) , don't care about others.

            Guidelines:
            - Analyze game log for objective metrics
            - Propose percentage splits (0-100%) with justification
            - Adjust offers based on evidence
            - Maximum {self.max_negotiation_round} round.
           
            """
            
            negotiate_prompt += add_log_to_prompt(self.log_dir)     
            negotiate_prompt += 'The description of actions and their rewards are as following' + '\n' + _create_system_message()

            negotiate_prompt += """

            Format: 
            <s>[Your analysis of contributions of others] 
            [Proposed distribution with rationale] 
            [Response to previous offer if applicable]</s>

            Example(for Agent2), it the team wins the game, use reward, else use punishment:
            <s> Agent1 30% team reward/punishment beacuse ..., Agent3 20% team reward/punishment beacuse ..., Agent4 20% team reward/punishment beacuse ....
            I can adjust if you show different metrics.</s> 

            or if others gave proposal before, you can also say :
            <s>I accept/reject XX's proposal , beacuse ....... </s>
            """
            if pre:
                previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                    self.previous_message)
                negotiate_prompt += previous_messages

        if sum:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                    self.previous_message)
            negotiate_prompt = """
            You are the decider and need to make a final decision according to the negotiation rounds between players.
            """
            negotiate_prompt += previous_messages 
            negotiate_prompt += f"""
            ### Negotiation Summary
            After the negotiation, please give a conclusion of the team reward allocation and give the final decision.

            Format: 
            <s>[Your analysis of contributions according to the negotiation] 
            [The final decision of the reward allocation for each player]</s>

            ###Example(Surround your message with '<s>' and '</s>' to indicate the start and end of your message, it the team wins the game, use reward in reward/punishment, else use punishment.):
            
            <s>Based on the previous consersation, i will give a summary and reach the final decision: According to the negotiation, ......  The final decision is : Agent1 30% team reward/punishment beacuse ..., Agent2 20% team reward/punishment beacuse ..., Agent3 20% team reward/punishment beacuse ..., Agent4 20% team reward/punishment beacuse ....
            This is the final reward for each player.</s>
            """ 

            negotiate_prompt = self.game_setting + negotiate_prompt

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message
            except:
                time.sleep(0.1)


