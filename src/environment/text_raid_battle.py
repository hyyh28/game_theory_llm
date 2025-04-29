import random

PLAYER_STATS = {
    'Warrior': {'hp': 800},
    'Mage1': {'hp': 400},
    'Mage2': {'hp': 400},
    'Priest': {'hp': 500},
}

MAX_BOSS_HP = 2500

actions = {
    'Warrior': ['Taunt', 'Shield Block', 'Charge'],
    'Mage1': ['Fireball', 'Pyroblast', 'Frostbolt'],
    'Mage2': ['Fireball', 'Pyroblast', 'Frostbolt'],
    'Priest': ['Heal', 'Mass Heal', 'Attack']
}

agents = ['Warrior', 'Mage1', 'Mage2', 'Priest']

class BattleEngine:
    def __init__(self, policy_dict=None):
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
            'taunt_timer': 0,
            'players': {
                name: {'hp': PLAYER_STATS[name]['hp'], 'shielded': False, 'max_hp': PLAYER_STATS[name]['hp']}
                for name in PLAYER_STATS
            }
        }
        self.n_agents = len(PLAYER_STATS)
        self.cooldowns = {name: {} for name in PLAYER_STATS}
        self.policy_dict = policy_dict
        self.turn_log = []
        self.turn = 0
        self.max_turn = 10

    def reset(self):
        """Reset the battle to initial state"""
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
            'taunt_timer': 0,
            'players': {
                name: {'hp': PLAYER_STATS[name]['hp'], 'shielded': False, 'max_hp': PLAYER_STATS[name]['hp']}
                for name in PLAYER_STATS
            }
        }
        self.cooldowns = {name: {} for name in PLAYER_STATS}
        self.turn_log = []
        self.turn = 0
        return self.state

    def is_over(self):
        if all(p['hp'] <= 0 for p in self.state['players'].values()):
            return True
        if self.turn >= self.max_turn:
            return True
        return False

    def step(self, action):
        """Execute one full turn (all agents + boss) and return rewards"""
        actions = {}
        order = ['Warrior', 'Mage1', 'Mage2', 'Priest']
        i = 0
        # Player turns
        for agent in order:
            if self.state['players'][agent]['hp'] <= 0:
                continue
            # action = self.policy_dict[agent](agent, self.state, self.cooldowns)
            actions[agent] = action[i]
            self.execute_action(agent, action[i])
            i += 1

        # Boss turn
        self.boss_turn()
        self.reduce_cooldowns()
        self.turn += 1

        # Calculate rewards
        rewards = self.calculate_reward(actions)

        # Check if battle is over
        done = self.is_over() or self.state['boss_hp'] <= 0

        return self.state, rewards, done, {}

    def calculate_reward(self, actions):
        """Calculate rewards for all agents based on actions taken"""
        rewards = {}
        if self.is_over():
            for agent in agents:
                rewards[agent] = -100
            return rewards

        # Base action rewards
        for agent, action in actions.items():
            rewards[agent] = self._base_action_reward(agent, action)

        # Additional reward/penalty based on game state
        if self.state['boss_hp'] <= 0:
            # Big reward for defeating boss
            for agent in rewards:
                rewards[agent] += 100
        return rewards
    
    def get_available_skills(self, agent: str) -> list:
        """
        Returns a list of skill names that are currently NOT on cooldown for the specified agent
        
        Args:
            agent: Name of the character (e.g. 'Warrior', 'Mage1')
        
        Returns:
            List of available skill names
        """
        # Define all possible skills for each role
        role_skills = {
            'Warrior': ['Taunt', 'Shield Block', 'Charge'],
            'Mage1': ['Fireball', 'Pyroblast', 'Frostbolt'],
            'Mage2': ['Fireball', 'Pyroblast', 'Frostbolt'],  # For Mage1/Mage2
            'Priest': ['Heal', 'Mass Heal', 'Attack']
        }
        
        # Determine role (handles Mage1/Mage2 cases)
        role = 'Mage' if 'Mage' in agent else agent
        
        # Get current cooldowns for this agent
        current_cooldowns = self.cooldowns.get(agent, {})
        
        # Filter skills that are either:
        # 1. Not in cooldowns dict at all, or
        # 2. Have cooldown value <= 0
        available = [
            skill for skill in role_skills[role]
            if current_cooldowns.get(skill, 0) <= 0
        ]
        
        return available

    def _base_action_reward(self, agent: str, action: str) -> float:
        role_actions = {
            'Warrior': {'Taunt': 2.0, 'Shield Block': 1.5, 'Charge': 1.0},
            'Mage1': {'Fireball': 1.8, 'Pyroblast': 2.5, 'Frostbolt': 1.2},
            'Mage2': {'Fireball': 1.8, 'Pyroblast': 2.5, 'Frostbolt': 1.2},
            'Priest': {'Heal': 2.0, 'Mass Heal': 3.0, 'Attack': 0.5}
        }
        return role_actions[agent].get(action, 0.0)

    def execute_action(self, agent, action):
        """
        Execute an action based only on skill name, automatically determining:
        - Target (Boss/Player/Self)
        - Effect value
        - Cooldown duration

        Args:
            agent: Name of the acting agent
            action: Dictionary containing only {"skill": skill_name}
        """
        skill = action

        # Default values
        target = None
        value = 0
        cooldown = 0

        # Warrior skills
        if agent == 'Warrior':
            if skill == 'Taunt':
                target = 'Boss'
                cooldown = 3
                self.cooldowns[agent][skill] = cooldown
                log = f"{agent} uses {skill}"
                self.state['aggro'] = agent
                self.state['taunt_timer'] = 3
                log += " (gaining aggro)"
                self.turn_log.append(log)
                return

            elif skill == 'Shield Block':
                target = agent  # Self-target
                cooldown = 2
                self.cooldowns[agent][skill] = cooldown
                log = f"{agent} uses {skill}"
                self.state['players'][agent]['shielded'] = True
                log += " (gaining shield)"
                self.turn_log.append(log)
                return

            elif skill == 'Charge':
                target = 'Boss'
                value = random.randint(50, 70)

        # Mage skills (Mage1/Mage2)
        elif 'Mage' in agent:
            if skill == 'Pyroblast':
                target = 'Boss'
                value = random.randint(150, 180)
                cooldown = 3
            elif skill == 'Fireball':
                target = 'Boss'
                value = random.randint(100, 130)
            elif skill == 'Frostbolt':
                target = 'Boss'
                value = random.randint(90, 110)

        # Priest skills
        elif agent == 'Priest':
            if skill == 'Mass Heal':
                target = agent
                value = random.randint(80, 100)
                cooldown = 3
            elif skill == 'Heal':
                # Find most injured ally (excluding dead players)
                valid_players = [p for p in self.state['players']
                                 if self.state['players'][p]['hp'] > 0 and p != agent]
                if valid_players:
                    target = min(valid_players,
                                 key=lambda p: self.state['players'][p]['hp'])
                    value = random.randint(150, 200)
            elif skill == 'Attack':
                target = 'Boss'
                value = random.randint(50, 70)

        # Execute the effects
        log = f"{agent} uses {skill}"

        # 1. Handle Boss attacks
        if target == 'Boss':
            self.state['boss_hp'] = max(0, self.state['boss_hp'] - value)
            log += f" {agent} attacks on Boss for {value} damage"

        # 2. Handle player targeting
        elif target in self.state['players']:
            if skill in 'Heal':
                max_hp = PLAYER_STATS[target]['hp']
                self.state['players'][target]['hp'] = min(
                    max_hp,
                    self.state['players'][target]['hp'] + value
                )
                log += f"Heal on {target} for {value} healing"
            elif skill in 'Mass Heal':
                for player in self.state['players']:
                    if self.state['players'][player]['hp'] > 0:
                        self.state['players'][player]['hp'] = min(
                            PLAYER_STATS[player]['hp'],
                            self.state['players'][player]['hp'] + value
                        )
                log = f"{agent} uses Mass Heal (all allies +{value} HP)"

        self.cooldowns[agent][skill] = cooldown
        self.turn_log.append(log)

    # def execute_action(self, agent, action):
    #     skill = action.get("skill")
    #     target = action.get("target")
    #     value = action.get("value", 0)

    #     log = f"{agent} uses {skill}"
    #     if target == "Boss":
    #         self.state['boss_hp'] = max(0, self.state['boss_hp'] - value)
    #         log += f" on Boss for {value} dmg"
    #     elif target in self.state['players']:
    #         if skill in ["Heal", "Mass Heal"]:
    #             self.state['players'][target]['hp'] = min(
    #                 PLAYER_STATS[target]['hp'],
    #                 self.state['players'][target]['hp'] + value
    #             )
    #             log += f" on {target} for {value} HP"
    #     if skill == 'Taunt':
    #         self.state['aggro'] = agent
    #     if skill == 'Shield Block':
    #         self.state['players'][agent]['shielded'] = True

    #     self.cooldowns[agent][skill] = action.get("cooldown", 0)
    #     self.turn_log.append(log)

    def boss_turn(self):
        """Boss attack logic with:
        - Taunt duration tracking
        - 50% damage reduction from shields
        """
        log = []
        
        # Taunt timer countdown
        # Determine attack mode
        warrior = 'Warrior'
        has_aggro = (self.state.get('aggro') == warrior and 
                    self.state['players'][warrior]['hp'] > 0 and
                    'taunt_timer' in self.state)

        if has_aggro:
            target = warrior
            base_dmg = 200
            attack_msg = f"Crushing Blow on {warrior}"
        else:
            valid_targets = [p for p in self.state['players'] 
                            if self.state['players'][p]['hp'] > 0]
            targets = sorted(valid_targets, 
                            key=lambda p: self.state['players'][p]['hp'])[:2]
            base_dmg = 100
            attack_msg = "Dark Blast on " + " and ".join(targets)

        # Apply damage with shield check
        damaged_targets = []
        for t in ([target] if has_aggro else targets):
            if self.state['players'][t].get('shielded', False):
                mitigated_dmg = base_dmg // 2
                self.state['players'][t]['hp'] = max(0, self.state['players'][t]['hp'] - mitigated_dmg)
                log.append(f"{attack_msg} ({mitigated_dmg} damage after 50% shield reduction)")
                self.state['players'][t]['shielded'] = False  # Shield consumed
            else:
                self.state['players'][t]['hp'] = max(0, self.state['players'][t]['hp'] - base_dmg)
                log.append(f"{attack_msg} for {base_dmg} damage")
            damaged_targets.append(t)
        
        if 'taunt_timer' in self.state:
            self.state['taunt_timer'] -= 1
            if self.state['taunt_timer'] <= 0:
                del self.state['taunt_timer']
                self.state['aggro'] = None
                log.append("Taunt effect expired")


        self.turn_log.extend(log)

    def reduce_cooldowns(self):
        for agent in self.cooldowns:
            for skill in list(self.cooldowns[agent].keys()):
                if self.cooldowns[agent][skill] > 0:
                    self.cooldowns[agent][skill] -= 1

    def print_state(self):
        print("=== Battle State ===")
        print(f"Boss HP: {self.state['boss_hp']} HP")
        for p in self.state['players']:
            hp = self.state['players'][p]['hp']
            print(f"{p}: {hp} HP")
        print("--- Turn Log ---")
        for l in self.turn_log:
            print(l)
        print("==================\n")
        self.turn_log.clear()

    def generate_global_prompt(self):
        state = self.state

        # Calculate battle metrics
        alive_count = sum(1 for p in state['players'].values() if p['hp'] > 0)
        boss_hp_percent = state['boss_hp'] / MAX_BOSS_HP
        shielded_players = sum(1 for p in state['players'].values() if p['shielded'])

        # Build prompt sections
        prompt = f"""=== RAID BATTLE STATUS===

        [BOSS STATUS]
        - HP: {state['boss_hp']}/{MAX_BOSS_HP} ({boss_hp_percent:.1%})
        - Current Aggro: {state['aggro'] or "None"}

        [PARTY STATUS] ({alive_count}/4 alive | {shielded_players} shielded)
        """

        # Add detailed player status
        for name in ['Warrior', 'Mage1', 'Mage2', 'Priest']:
            player = state['players'][name]
            status = []

            # Health status
            if player['hp'] <= 0:
                status.append("DEAD")
            else:
                hp_percent = player['hp'] / player['max_hp']
                status.append(f" {player['hp']}/{player['max_hp']} ({hp_percent:.0%})")

                # Special statuses
                if player['shielded']:
                    status.append("SHIELDED")
                if state['aggro'] == name:
                    status.append("AGGRO")

            # Cooldowns
            cds = [f"{k}({v})" for k, v in self.cooldowns[name].items() if v > 0]

            prompt += f"""
            [{name.upper()}]
            - Status: {', '.join(status)}
            - Cooldowns: {', '.join(cds) if cds else 'None'}
            """

        # Add battle log
        battle_log = '\n'.join(self.turn_log[-3:]) if self.turn_log else 'No actions recorded yet'
        prompt += f"""
                [BATTLE LOG]
                {battle_log}
                """

        # Add detailed action spaces for each agent type
        prompt += """
            [RESPONSE INSTRUCTIONS]
            Each agent must respond with ONLY their action number (1-3)
            based on their role and current status.
            """

        prompt += f"""
            The information of your round and the max round.
            MAX_round = {self.max_turn}
            Current round = {self.turn}
            """

        return prompt


# def fake_policy(agent, state, cooldowns):
#     if agent == 'Warrior':
#         if cooldowns[agent].get("Taunt", 0) == 0:
#             return {"skill": "Taunt", "target": "Boss", "value": 0, "cooldown": 3}
#         elif cooldowns[agent].get("Shield Block", 0) == 0 and state["players"][agent]["hp"] < 400:
#             return {"skill": "Shield Block", "target": agent, "value": 0, "cooldown": 2}
#         else:
#             return {"skill": "Charge", "target": "Boss", "value": random.randint(50, 70), "cooldown": 0}

#     elif "Mage" in agent:
#         if cooldowns[agent].get("Arcane Blast", 0) == 0:
#             return {"skill": "Arcane Blast", "target": "Boss", "value": random.randint(150, 180), "cooldown": 3}
#         elif random.random() < 0.5:
#             return {"skill": "Fireball", "target": "Boss", "value": random.randint(100, 130), "cooldown": 0}
#         else:
#             return {"skill": "Frostbolt", "target": "Boss", "value": random.randint(90, 110), "cooldown": 0}

#     elif agent == "Priest":
#         low_hp_players = sorted(
#             [p for p in state["players"] if state["players"][p]["hp"] < state["players"][p]["max_hp"] * 0.6 and state["players"][p]["hp"] > 0],
#             key=lambda p: state["players"][p]["hp"]
#         )
#         if cooldowns[agent].get("Mass Heal", 0) == 0 and len(low_hp_players) >= 2:
#             return {"skill": "Mass Heal", "target": "All", "value": random.randint(80, 100), "cooldown": 3}
#         elif low_hp_players:
#             target = low_hp_players[0]
#             return {"skill": "Heal", "target": target, "value": random.randint(150, 200), "cooldown": 0}
#         else:
#             return {"skill": "Idle", "target": None, "value": 0, "cooldown": 0}

import argparse
from model import call_api
import time
import numpy as np
import re
from typing import Dict, List, Tuple


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


# def _create_system_message(role_type) -> str:
#     role_descriptions = {
#         'Warrior': (
#             "Warrior (Tank)",
#             "Your responsibilities:\n"
#             "- Maintain enemy focus on yourself\n"
#             "- Protect teammates with defensive skills\n"
#             "- Control enemy positioning\n\n"
#             "Your skills:\n"
#             "Taunt: Force enemies to attack you, and you will get reward if you choose this action.\n"
#             "Shield Block: Reduce incoming damage, and you will get reward if you choose this action.\n"
#             "Charge: Close distance quickly, and you will get reward if you choose this action."
#         ),
#         'Mage1': (
#             "Mage (Damage Dealer)",
#             "Your responsibilities:\n"
#             "- Deal maximum damage to enemies\n"
#             "- Avoid dangerous areas\n"
#             "- Conserve mana for critical moments\n\n"
#             "Your skills:\n"
#             "Fireball: Reliable fire damage, and you will get reward if you choose this action.\n"
#             "Pyroblast: High burst damage, and you will get reward if you choose this action.\n"
#             "Frostbolt: Slows enemy movement, and you will get reward if you choose this action."
#         ),
#         'Mage2': (
#             "Mage (Damage Dealer)",
#             "Your responsibilities:\n"
#             "- Deal maximum damage to enemies\n"
#             "- Avoid dangerous areas\n"
#             "- Conserve mana for critical moments\n\n"
#             "Your skills:\n"
#             "Fireball: Reliable fire damage, and you will get reward if you choose this action.\n"
#             "Pyroblast: High burst damage, and you will get reward if you choose this action.\n"
#             "Frostbolt: Slows enemy movement, and you will get reward if you choose this action."
#         ),
#         'Priest': (
#             "Priest (Healer)",
#             "Your responsibilities:\n"
#             "- Monitor and heal teammates\n"
#             "- Stay in safe positions\n"
#             "- Manage mana efficiently\n\n"
#             "Your skills:\n"
#             "Heal: Restore health to one ally, and you will get reward if you choose this action.\n"
#             "Mass Heal: Heal entire team, and you will get reward if you choose this action.\n"
#             "Idle: Recover mana when safe, and you will get reward if you choose this action."
#         )
#     }

#     name, spec = role_descriptions[role_type]
#     return f"Your role is {name}\n{spec}\nRemember to communicate with your team and adapt to battle conditions."

def _create_system_message(role_type) -> str:
    """Generate role-specific system prompt messages"""
    # Configurable parameters
    skill_details = {
        'Warrior': {
            'Taunt': {'reward': 2.0, 'cooldown': 3, 'effect': "Forces enemies to attack you for 3 turns"},
            'Shield Block': {'reward': 1.5, 'cooldown': 2, 'effect': "Reduces next incoming damage by 50%"},
            'Charge': {'reward': 1.0, 'effect': f"Deals {random.randint(50,70)} damage"}
        },
        'Mage1': {
            'Fireball': {'reward': 1.8, 'effect': f"Deals {random.randint(100,130)} fire damage"},
            'Pyroblast': {'reward': 2.5, 'cooldown': 3, 'effect': f"Channels to deal {random.randint(150,180)} explosive damage"},
            'Frostbolt': {'reward': 1.2, 'effect': f"Deals {random.randint(90,110)} frost damage and slows"}
        },
        'Mage2': {
            'Fireball': {'reward': 1.8, 'effect': f"Deals {random.randint(100,130)} fire damage"},
            'Pyroblast': {'reward': 2.5, 'cooldown': 3, 'effect': f"Channels to deal {random.randint(150,180)} explosive damage"},
            'Frostbolt': {'reward': 1.2, 'effect': f"Deals {random.randint(90,110)} frost damage and slows"}
        },
        'Priest': {
            'Heal': {'reward': 2.0, 'effect': f"Restores {random.randint(150,200)} HP to single target"},
            'Mass Heal': {'reward': 3.0, 'cooldown': 3, 'effect': f"Heals all allies for {random.randint(80,100)} HP"},
            'Attack': {'reward': 0.5, 'effect': f"Deals {random.randint(50,70)} damage"}
        }
    }

    role_info = {
        'Warrior': {
            'name': "Warrior (Tank)",
            'responsibilities': [
                "Maintain enemy aggro using Taunt",
                "Mitigate critical damage with Shield Block",
                "Protect backline healers and DPS"
            ]
        },
        'Mage1': {
            'name': "Mage1 (Damage Dealer)",
            'responsibilities': [
                "Maximize damage output",
                "Manage mana consumption",
                "Avoid dangerous areas"
            ]
        },
        'Mage2': {
            'name': "Mage2 (Damage Dealer)",
            'responsibilities': [
                "Maximize damage output",
                "Manage mana consumption",
                "Avoid dangerous areas"
            ]
        },
        'Priest': {
            'name': "Priest (Healer)",
            'responsibilities': [
                "Monitor team health status",
                "Optimize healing resource allocation",
                "Keep yourself alive"
            ]
        }
    }

    # Select correct role configuration
    role_key = role_type
    info = role_info[role_key]
    skills = skill_details[role_key]
    
    # Build skill descriptions
    skill_descriptions = []
    for skill, params in skills.items():
        desc = f"{skill}: {params['effect']}"
        if 'cooldown' in params:
            desc += f" (Cooldown: {params['cooldown']} turns)"
        desc += f" - Action reward: {params['reward']} pts"
        skill_descriptions.append(desc)

    # Compose complete prompt
    responsibilities_str = '\n'.join(f'• {resp}' for resp in info['responsibilities'])
    skills_str = '\n'.join(f'• {desc}' for desc in skill_descriptions)

    prompt = f"""You are [[ {info['name']} ]] in the game
        
    Primary Responsibilities:
    {responsibilities_str}

    Available Skills:
    {skills_str}

    Combat Strategy:
    1. Prioritize your core responsibilities
    2. Track skill cooldowns
    3. Maintain communication with teammates
    4. Adapt tactics based on battle conditions
    """
    return prompt

import os
import json

def append_to_json(new_data, filename='./result/raid_gift.json'):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            existing_data = json.load(file)
    else:
        existing_data = []
    
    existing_data.append(new_data)
    
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(existing_data, file, ensure_ascii=False, indent=2)

class Agent:
    def __init__(self, args, name, env):
        self.args = args
        self.name = name
        self.env = env
        self.the_other_player = self.other_player(self.name)
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []
        self.n_agents = len(agents)
        self.actions = actions[name]
        self.gift = np.zeros((self.n_agents, self.n_agents), dtype=float)
        self.game_setting = f"""
        ### Raid Battle Introduction
        You are participating in a challenging raid battle with your team against a powerful boss. 
        Your team consists of {self.n_agents} players with different roles: {', '.join(agents)}.
        You are playing as {self.name}. 

        ### Battle Mechanics
        - Each round consists of a preparation phase and an execution phase
        - During preparation, you can discuss strategy with teammates
        - During execution, you must select one action from available actions: {self.actions}
        - The boss has will attack 2 players with the lowest hp each round if not arrgo by the warrior, otherwise it will attack warrior only.
        - The game will fail if the round >= max_round, so take care of the remaining rounds.
        
        ### Reward function
        - The reward for each agent consists of both individual and team components. The individual reward is given for each action selected, while the team reward is +100 for winning and -100 otherwise. 
        The team reward can be allocated to each agent (e.g., evenly distributing 25 per agent if the team wins, or through negotiation to assign different proportions).

        """

        # self.prompt_for_negotiate = {
        #     0: '',
        #     1: "Consider your teammates' suggestions carefully, but remember your role responsibilities.\n",
        #     2: "Evaluate whether the proposed strategy aligns with your role and the team's needs.\n",
        #     3: "As {}, you should prioritize {} in your decision.\n",
        #     4: "The current battle phase requires you to focus on {}.\n",
        #     5: "The boss is preparing {}, adjust your strategy accordingly.\n",
        #     6: "Balance team coordination with your role's specific duties.\n",
        # }

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


        ### Available Actions
        Please select one action from the following options:
        {self.actions}
        Pay attention do not choose actions in cooling time according to the current state !!
        

        ### Response Format
        Your response must contain exactly one action from the list above,
        formatted as: <s>selected_action</s>
        """

        # Append negotiation history if exists
        # ;;;;;;;;;;;;;;;;;;;;;;;;;;;;
        if pre:
            pre_message = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message) + "\n\nPlease take the negotiation messages into consideration and make your own decision.\n"
            action_prompt += "\n\n### Negotiation History\n" + "\n".join(pre_message)
        action_prompt = self.game_setting + '\n' + _create_system_message(self.name) + '\n' + 'Current state : {}'.format(
            self.args.state_prompt) + '\n' + action_prompt
        print(f'----------------- {self.name} Decide to make action ---------------------')
        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                print(action_message)
                print('-' * 20)
                action = parse_action(action_message, self.actions)
                formatted_msg = f'{self.name} makes action: {action}'
                append_to_json(formatted_msg)
                return action
            except:
                print(Exception)
                time.sleep(0.1)

    def negotiation(self, pre=True, gift=True):

        negotiate_prompt = f"""
                ### Negotiation
                Your Hp is {self.env.state['players'][self.name]['hp']}, if your HP <=0, you are dead and should terminate with format: "<s>halt negotiation</s>".
                Otherwise, you can discuss with {self.other_player(self.name)} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
                Analyze the situation and decide on what to say to the other player. You can offer an advice to influence the other player's decision.
                Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Mage2, '<s>Hi, how are you guys?</s>' or '<s>I suggest Warrior to choose action_X, 
                I suggest Mage1 to choose action_Y, and I suggest Priest to choose action_Z</s>'.
                You can also choose to halt the negotiation by saying 'halt negotiation', but you are encouraged to discuss with others or give advice instead of end the talk easily.
                """
        if gift:
            negotiate_prompt = f"""
            ### Negotiation
            Your Hp is {self.env.state['players'][self.name]['hp']}, if your HP <=0, you are dead and should terminate with format: "<s>halt negotiation</s>".
            Otherwise, you can discuss with {self.other_player(self.name)} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
            Analyze the situation and decide on what to say to the other player. You can offer a percentage of your final team reward (0-100%) to influence the other player's decision.
            If you feel the other player’s offer is too high (they are asking for too much) or too low (they are offering too little), you can request them to lower or raise their offer accordingly.
            Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Mage2, '<s>Hi, how are you guys?</s>' or '<s>I will give Warrior 10% of my final team reward if he choose action_X, 
            I will give Mage1 10% of my final team reward if he choose action_Y, and I will give Priest 5% of my final team reward if he choose action_Z</s>'.
            """
            negotiate_prompt += """
            First, **analyze the current negotiation situation step-by-step based on Shapley Value principles**:
            
            - Step 1: What is the potential total reward if both players cooperate?
            - Step 2: Without detailed calculation, intuitively consider:
                - How much do you individually contribute to the success of cooperation?
                - How much does the other player contribute?
            - Step 3: According to Shapley Value thinking:
                - Fair rewards should reflect each player's marginal contribution to cooperation.
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


        negotiate_prompt += 'Current state : {}'.format(self.args.state_prompt)

        if pre:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + negotiate_prompt
    #     negotiate_prompt += """
    #     ### Your tasks:
    #     1. EVALUATE received suggestions:
    #    - Check if suggestions benefit your role
    #    - Verify alignment with game state and team's goal
    #    - Respond with: 
    #      * "<s>Accept: [reason]</s>" 
    #      * "<s>Reject: [reason]</s>"
    #      * "<s>Counter: [alternative]</s>"

    #     2. DECIDE when to end:
    #     - Terminate with format: "<s>halt negotiation</s>"
    #     """

        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message
            except:
                time.sleep(0.1)


    def _update_gift_matrix(self, speaker: str, message: str):
        if '<s>' not in message or '</s>' not in message:
            return

        start = message.index('<s>') + len('<s>')
        end = message.index('</s>')
        content = message[start:end].strip()
        pattern = r"I will give (\w+) (\d+)% of my reward if he choose (\w+)"
        matches = re.finditer(pattern, content)

        for match in matches:
            target = match.group(1)
            offer_pct = int(match.group(2)) / 100
            action = match.group(3)
            if target not in self.agents:
                continue
            speaker_idx = self.agents.index(speaker)
            target_idx = self.agents.index(target)
            self.gift[speaker_idx][target_idx] = max(
                self.gift[speaker_idx][target_idx],
                offer_pct
            )
            if not hasattr(self, 'action_requests'):
                self.action_requests = {}
            self.action_requests[(speaker, target)] = action


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='raid')
    parser.add_argument('--max_negotiation_round', type=int, default=1)
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--state_prompt', type=str, default="rational")
    parser.add_argument('--model', type=str, default='deepseek')
    args = parser.parse_args()
    engine = BattleEngine()
    result_save_dir = './result/raid_gift.json'
    args.system_prompt = f'You are a {args.system_prompt} assistant that carefully answer the question.'
    max_n = args.max_negotiation_round
    agents_chat = {'Warrior': Agent(args, 'Warrior', engine),
                   'Mage1': Agent(args, 'Mage1', engine),
                   'Mage2': Agent(args, 'Mage2', engine),
                   'Priest': Agent(args, 'Priest', engine)}
    # policy = {
    #     "Warrior": fake_policy,
    #     "Mage1": fake_policy,
    #     "Mage2": fake_policy,
    #     "Priest": fake_policy,
    # }
    d = False
    while not d:
        args.state_prompt = engine.generate_global_prompt()
        print('------------------------Negotiation begins-----------------------------')
        for i in range(0, max_n):
            for ag in agents:
                msg = agents_chat[ag].negotiation()
                agents_chat[ag].previous_message.append('{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + 'in game turn {}'.format(engine.turn) + msg)
                for oth in agents_chat[ag].the_other_player:
                    agents_chat[oth].previous_message.append(
                        '{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + 'in game turn {}'.format(engine.turn) + msg)
                formatted_msg = f"{ag} said in negotiation round {i + 1} in game turn {engine.turn}: {msg}."
                print(formatted_msg)
                append_to_json([formatted_msg], result_save_dir)
                if msg == '<s>halt negotiation</s>':
                    break
        print('------------------------Negotiation ends-----------------------------')
        actions = []
        for i in agents:
            actions.append(agents_chat[i].make_action())
        for ag in agents:
            agents_chat[ag].previous_message = []
        s, r, d, _ = engine.step(actions)
        engine.print_state()
        append_to_json(engine.turn_log, result_save_dir)
        if engine.is_over():
            print('------------------------ Fail to defeat boss.------------------------')
        if engine.state['boss_hp'] <= 0:
            print('----------------------------WIN----------------------')
        
