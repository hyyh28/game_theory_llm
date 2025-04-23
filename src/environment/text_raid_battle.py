import random

PLAYER_STATS = {
    'Warrior': {'hp': 800},
    'Mage1': {'hp': 400},
    'Mage2': {'hp': 400},
    'Priest': {'hp': 500},
}

MAX_BOSS_HP = 1500


class BattleEngine:
    def __init__(self, policy_dict=None):
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
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
        if self.state['boss_hp'] <= 0:
            return True
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
            self.execute_action(agent, action)
            i += 1

        # Boss turn
        self.boss_turn()
        self.reduce_cooldowns()
        self.turn += 1

        # Calculate rewards
        rewards = self.calculate_reward(actions)

        # Check if battle is over
        done = self.is_over()

        # Apply timeout penalty if no one won in max_turn turns
        if self.turn >= self.max_turn and not (
                self.state['boss_hp'] <= 0 or all(p['hp'] <= 0 for p in self.state['players'].values())):
            for agent in rewards:
                rewards[agent] = -100

        return self.state, rewards, done, {}

    def calculate_reward(self, actions):
        """Calculate rewards for all agents based on actions taken"""
        rewards = {}

        # If battle is already over, return 0 rewards
        if self.is_over():
            for agent in actions:
                rewards[agent] = -100
            return rewards

        # Base action rewards
        for agent, action in actions.items():
            rewards[agent] = self._base_action_reward(agent, action['skill'])

        # Additional reward/penalty based on game state
        if self.state['boss_hp'] <= 0:
            # Big reward for defeating boss
            for agent in rewards:
                rewards[agent] += 100
        elif all(p['hp'] <= 0 for p in self.state['players'].values()):
            # Penalty for team wipe
            for agent in rewards:
                rewards[agent] -= 50

        return rewards

    def _base_action_reward(self, agent: str, action: str) -> float:
        role_actions = {
            'Warrior': {'Taunt': 2.0, 'Shield Block': 1.5, 'Charge': 1.0},
            'Mage1': {'Fireball': 1.8, 'Arcane Blast': 2.5, 'Frostbolt': 1.2},
            'Mage2': {'Fireball': 1.8, 'Arcane Blast': 2.5, 'Frostbolt': 1.2},
            'Priest': {'Heal': 2.0, 'Mass Heal': 3.0, 'Idle': 0.5}
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
            elif skill == 'Shield Block':
                target = agent  # Self-target
                cooldown = 2
            elif skill == 'Charge':
                target = 'Boss'
                value = random.randint(50, 70)

        # Mage skills (Mage1/Mage2)
        elif 'Mage' in agent:
            if skill == 'Arcane Blast':
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
                target = 'All'
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
            elif skill == 'Idle':
                pass  # No effect

        # Execute the effects
        log = f"{agent} uses {skill}"

        # 1. Handle Boss attacks
        if target == 'Boss':
            self.state['boss_hp'] = max(0, self.state['boss_hp'] - value)
            log += f" on Boss for {value} damage"

        # 2. Handle player targeting
        elif target in self.state['players']:
            if skill in ['Heal', 'Mass Heal']:
                max_hp = PLAYER_STATS[target]['hp']
                self.state['players'][target]['hp'] = min(
                    max_hp,
                    self.state['players'][target]['hp'] + value
                )
                log += f" on {target} for {value} healing"

        # 3. Handle special effects
        if skill == 'Taunt':
            self.state['aggro'] = agent
            log += " (gaining aggro)"
        elif skill == 'Shield Block':
            self.state['players'][agent]['shielded'] = True
            log += " (gaining shield)"

        # 4. Apply cooldowns if action was successful
        if target is not None:  # Only apply CD if action had valid target
            self.cooldowns[agent][skill] = cooldown
        else:
            log += " (failed - no valid target)"

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
        log = "Boss uses "
        aggro = self.state['aggro']
        if aggro != 'Warrior':
            targets = sorted(
                [p for p in self.state['players'] if self.state['players'][p]['hp'] > 0],
                key=lambda p: self.state['players'][p]['hp']
            )[:2]
            for t in targets:
                self.state['players'][t]['hp'] -= 300
            log += f"Dark Blast on {targets} for 300 dmg each"
        else:
            for p in self.state['players']:
                if self.state['players'][p]['hp'] > 0:
                    self.state['players'][p]['hp'] -= 100
            log += "Roar (AOE 100 dmg to all)"

        self.turn_log.append(log)

    def reduce_cooldowns(self):
        for agent in self.cooldowns:
            for skill in list(self.cooldowns[agent].keys()):
                if self.cooldowns[agent][skill] > 0:
                    self.cooldowns[agent][skill] -= 1

    def print_state(self):
        print("=== Battle State ===")
        print(f"Boss HP: {self.state['boss_hp']}")
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
            [AGENT ACTION SPACES]

            [WARRIOR ACTIONS]
            1. Charge (Deal 50-70 damage to boss)
            2. Taunt (Force boss aggro, CD:3)
            3. Shield Block (Gain damage shield, CD:2) 

            [MAGE ACTIONS]
            1. Arcane Blast (Deal 150-180 damage, CD:3)
            2. Fireball (Deal 100-130 damage)
            3. Frostbolt (Deal 90-110 damage)

            [PRIEST ACTIONS]
            1. Heal (Restore 150-200 HP to ally)
            2. Mass Heal (Restore 80-100 HP to all, CD:3)
            3. Idle (Do nothing)

            [RESPONSE INSTRUCTIONS]
            Each agent must respond with ONLY their action number (1-3)
            based on their role and current status.
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


def _create_system_message(role_type) -> str:
    role_specs = {
        'Warrior': (
            "Warrior",
            "You are the main tank responsible for controlling the battle rhythm.\n\n"
            "Skill List:\n"
            "Taunt: Forces enemies to attack you\n"
            "Shield Block: Reduces incoming damage\n"
            "Charge: Quickly closes distance to target\n\n"
        ),
        'Mage_1': (
            "Mage",
            "You are one of the team's primary damage dealers.\n\n"
            "Skill List:\n"
            "Fireball: Basic fire damage spell\n"
            "Pyroblast: High damage with cast time\n"
            "Frostbolt: Basic frost damage spell\n"
            "Blizzard: Area-of-effect damage\n\n"
        ),
        'Mage_2': (
            "Mage",
            "You are one of the team's primary damage dealers.\n\n"
            "Skill List:\n"
            "Fireball: Basic fire damage spell\n"
            "Pyroblast: High damage with cast time\n"
            "Frostbolt: Basic frost damage spell\n"
            "Blizzard: Area-of-effect damage\n\n"
        ),
        'Priest': (
            "Priest",
            "You are the team's primary healer.\n\n"
            "Skill List:\n"
            "Heal: Single-target healing\n"
            "Mass Heal: Group healing\n"
            "Idle: Mana regeneration\n\n"
        )
    }

    name, spec = role_specs[role_type]
    sys_msg = f"Your role is {name}\n{spec}\n Remember to communicate clearly with your team and adapt to changing battle conditions."

    return sys_msg


actions = {
    'Warrior': ['Taunt', 'Shield Block', 'Charge'],
    'Mage_1': ['Fireball', 'Pyroblast', 'Frostbolt', 'Blizzard'],
    'Mage_2': ['Fireball', 'Pyroblast', 'Frostbolt', 'Blizzard'],
    'Priest': ['Heal', 'Mass Heal', 'Idle']
}

agents = ['Warrior', 'Mage_1', 'Mage_2', 'Priest']


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
        - The boss has will attack each round
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

    def make_action(self, name: str, pre=True) -> str:
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

        ### Response Format
        Your response must contain exactly one action from the list above,
        formatted as: <s>selected_action</s>
        """

        # Append negotiation history if exists
        if pre:
            pre_message = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message) + "\n\nPlease carefully analyze the negotiation messages, think about whether you can trust others' message, and make your own decision.\n"
            action_prompt += "\n\n### Negotiation History\n" + "\n".join(pre_message)
        action_prompt = self.game_setting + '\n' + _create_system_message(self.name) + '\n' + 'Current state {}'.format(
            self.args.system_prompt) + '\n' + action_prompt

        while True:
            try:
                action_message = call_api(self.args.model, action_prompt, self.args.system_prompt)
                print(action_message)
                print('-' * 20)
                action = parse_action(action_message, self.actions)
                return action
            except:
                print(Exception)
                time.sleep(0.1)

    def negotiation(self, pre=False, gift=False):

        negotiate_prompt = f"""
                ### Negotiation
                You can discuss with {self.other_player(self.name)} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
                Analyze the situation and decide on what to say to the other player. You can offer an advice to influence the other player's decision.
                Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Mage_2, '<s>Hi, how are you guys?</s>' or '<s>I suggest Warrior to choose action_X, 
                I suggest Mage_1 to choose action_Y, and I suggest Priest to choose action_Z</s>'.
                You can also choose to halt the negotiation by saying 'halt negotiation'.
                """
        if gift:
            negotiate_prompt = f"""
            ### Negotiation
            You can discuss with {self.other_player(self.name)} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
            Analyze the situation and decide on what to say to the other player. You can offer a percentage of your reward (0-100%) to influence the other player's decision.
            Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, for Mage_2, '<s>Hi, how are you guys?</s>' or '<s>I will give Warrior 30% of my reward if he choose action_X, 
            I will give Mage_1 20% of my reward if he choose action_Y, and I will give Priest 10% of my reward if he choose action_Z</s>'.
            You can also choose to halt the negotiation by saying 'halt negotiation'.
            """

        negotiate_prompt += 'Current state : {}'.format(self.args.system_prompt)

        if pre:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + negotiate_prompt
        negotiate_prompt += """
        ### Your tasks:
        1. EVALUATE received suggestions:
       - Check if suggestions benefit your role
       - Verify alignment with game state and team's goal
       - Respond with: 
         * "<s>Accept: [reason]</s>" 
         * "<s>Reject: [reason]</s>"
         * "<s>Counter: [alternative]</s>"

        2. DECIDE when to end:
        - Terminate with format: "<s>halt negotiation</s>"
        """

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
    parser.add_argument('--max_negotiation_round', type=int, default=0)
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    args = parser.parse_args()
    engine = BattleEngine()
    result_save_dir = f'result/raid_non.json'
    args.system_prompt = f'You are a {args.system_prompt} assistant that carefully answer the question.'
    max_n = args.max_negotiation_round
    agents_chat = {'Warrior': Agent(args, 'Warrior', engine),
                   'Mage_1': Agent(args, 'Mage_1', engine),
                   'Mage_2': Agent(args, 'Mage_2', engine),
                   'Priest': Agent(args, 'Priest', engine)}
    # policy = {
    #     "Warrior": fake_policy,
    #     "Mage1": fake_policy,
    #     "Mage2": fake_policy,
    #     "Priest": fake_policy,
    # }
    while not engine.is_over():
        args.system_prompt = engine.generate_global_prompt()
        for i in range(0, max_n):
            for ag in agents:
                msg = agents_chat[ag].negotiation()
                agents_chat[ag].previous_message.append('{}'.format(ag) + 'replied in round {}: '.format(i + 1) + msg)
                for oth in agents_chat[ag].other_agents:
                    agents_chat[oth].previous_message.append(
                        '{}'.format(ag) + 'replied in round {}: '.format(i + 1) + msg)
                if msg == '<s>halt negotiation</s>':
                    break
        actions = []
        for i in agents:
            actions.append(agents_chat[i].make_action())
        engine.step(actions)
        engine.print_state()
