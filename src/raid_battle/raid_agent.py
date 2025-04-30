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
			* +100 for victory / -100 for defeat
			* Default: Equal split(25 or -25 for each player)
			* Custom: Negotiate alternative distributions
        - Total : The sum of the above two rewards.
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
        
        You are {self.name} in the game.

        ### Available Actions
        
        Please select one action from the following options:
        {self.actions}
        Pay attention do not choose actions in cooling time according to the current state !!
        *** Remember if others use Taunt this round, do not use Taunt in this round !!！***
        
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
                formatted_msg = f'{self.name} makes action: {action}'
                return action
            except:
                print(Exception)
                time.sleep(0.1)

    def negotiation(self, pre=True, s_q=False):

        negotiate_prompt = f"""
                ### Negotiation
                Your Hp is {self.env.state['players'][self.name]['hp']}, if your HP <=0, you are dead and should terminate with format: "<s>halt negotiation</s>".

                Otherwise, you can discuss with {self.other_player(self.name)}. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
                You are self-interested, so your **goal** is to **maximize your own reward**.
                Analyze the situation and decide on what to say to the other player. You can offer an advice to influence the other player's decision.
                
                **Before you give the advice , you should analyze the step-by-step based on Shapley Value principles**:
            
                - Step 1: What is the potential total reward of all players?
                - Step 2: Without detailed calculation, intuitively consider:
                - How much is your individual reward if you take others' advice ?
                - How much can the other player contribute if he takes your advice?
                
                ### Template
                Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Agent2,  '<s>I suggest Agent1 to choose Taunt because there is no player arrgo the boss, 
                I suggest Agent3 to choose fireball because we need to cause damage, and I suggest Agent4 to choose heal beacuse my HP is quite low</s>'.

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
        negotiate_prompt = self.game_setting + negotiate_prompt

        if s_q:
            negotiate_prompt = f"""
            You are {self.name}. Discuss with {self.other_player(self.name)} to distribute team rewards proportionally based on:
            1. Each agent's measurable contributions (damage, healing, taunt)
            2. Critical actions that impacted outcomes
            3. Relative importance of each role

            Guidelines:
            - Analyze game log for objective metrics
            - Propose percentage splits (0-100%) with justification
            - Adjust offers based on evidence
            - Maximum {self.max_negotiation_round} rounds

            Format: 
            <s>[Your analysis of contributions] 
            [Proposed distribution with rationale] 
            [Response to previous offer if applicable]</s>

            Example(for Agent2):
            <s>Based on logged metrics: Agent1 30% team reward because he sacrifice his own reward to heal others, Agent3 20% team reward beacuse he deals most of the damage, Agent4 20% team reward beacuse he bears the most damage.
            I can adjust if you show different metrics.</s> or if others gave proposal before, you can also say <s> I accept/reject Agent3's proposal , beacuse ....... </s>
            """

            negotiate_prompt += add_log_to_prompt(self.log_dir)

            negotiate_prompt += """
            **You should analyze the step-by-step based on Shapley Value principles**:
            
            - Step 1: What is the potential total reward of all players?
            - Step 2: Without detailed calculation, intuitively consider:
                - How much do you individually contribute to the whole game?
                - How much does the other player contribute?
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
            """

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message
            except:
                time.sleep(0.1)

