import random

PLAYER_STATS = {
    'Agent1': {'hp': 600},
    'Agent2': {'hp': 600},
    'Agent3': {'hp': 600},
    'Agent4': {'hp': 600},
}

MAX_BOSS_HP = 3000

actions = ['Taunt', 'Fireball', 'Heal']

agents = ['Agent1', 'Agent2', 'Agent3', 'Agent4']

class BattleEngine:
    def __init__(self):
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
            'players': {
                name: {'hp': PLAYER_STATS[name]['hp'],  'max_hp': PLAYER_STATS[name]['hp']}
                for name in PLAYER_STATS
            }
        }
        self.n_agents = len(PLAYER_STATS)
        self.cooldowns = {name: {} for name in PLAYER_STATS}
        self.turn_log = []
        self.turn = 0
        self.max_turn = 10
        self.boss_damage = 400
        self.reward = {}

    def reset(self):
        """Reset the battle to initial state"""
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
            'players': {
                name: {'hp': PLAYER_STATS[name]['hp'], 'max_hp': PLAYER_STATS[name]['hp']}
                for name in PLAYER_STATS
            }
        }
        self.cooldowns = {name: {} for name in PLAYER_STATS}
        self.turn_log = []
        self.turn = 0
        self.reward = {}

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
        order = ['Agent1', 'Agent2', 'Agent3', 'Agent4']
        i = 0
        self.turn_log.append(f'--------The game log of turn {self.turn}--------\n')
        # Player turns
        for agent in order:
            if self.state['players'][agent]['hp'] <= 0:
                i += 1
                continue
            # action = self.policy_dict[agent](agent, self.state, self.cooldowns)
            actions[agent] = action[i]
            self.execute_action(agent, action[i])
            i += 1

        # Boss turn
        self.boss_turn()
        self.reduce_cooldowns()
        self.turn_log.append('----The following is the state now-----' + '\n' + self.generate_global_prompt() + '\n')
        self.turn += 1

        # Calculate rewards
        rewards = self.calculate_reward(actions)

        # Check if battle is over
        done = self.is_over() or self.state['boss_hp'] <= 0
        if done:
            if self.is_over():
                self.turn_log.append('----------- Fail to defeat the boss!!!')
            else:
                self.turn_log.append('----------- Win the game!!!')

        return self.state, rewards, done, {}

    def calculate_reward(self, action, f_r=25):
        """Calculate rewards for all agents based on actions taken"""
        if self.is_over():
            for agent in agents:
                self.reward[agent] = -f_r
            return self.reward

        # Base action rewards
        for agent, ac in action.items():
            self.reward[agent] = self._base_action_reward(ac)

        # Additional reward/penalty based on game state
        if self.state['boss_hp'] <= 0:
            # Big reward for defeating boss
            for agent in agents:
                self.reward[agent] = f_r
        return self.reward
    
    def get_available_skills(self, agent: str) -> list:
        """
        Returns a list of skill names that are currently NOT on cooldown for the specified agent
        
        Args:
            agent: Name of the character (e.g. 'Warrior', 'Mage1')
        
        Returns:
            List of available skill names
        """
        # Define all possible skills for each role
        role_skills = actions
        current_cooldowns = self.cooldowns.get(agent, {})
        available = [
            skill for skill in role_skills
            if current_cooldowns.get(skill, 0) <= 0
        ]
        
        return available

    def _base_action_reward(self, action: str) -> float:
        role_actions = {
            'Taunt':0.5, 'Fireball':2, 'Heal':0.5}
        return role_actions.get(action, 0.0)

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
        
        if skill == 'Taunt':
            target = 'Boss'
            cooldown = 3
            self.cooldowns[agent][skill] = cooldown
            log = f"{agent} uses {skill}"
            self.state['aggro'] = agent
            log += f" {agent} use Taunt\n"
            self.turn_log.append(log)
            return
        
        elif skill == 'Fireball':
            target = 'Boss'
            value = random.randint(100, 150)
      
        elif skill == 'Heal':
            valid_players = [p for p in self.state['players']
                                 if self.state['players'][p]['hp'] > 0 and p != agent]
            if valid_players:
                target = min(valid_players,
                                 key=lambda p: self.state['players'][p]['hp'])
                value = random.randint(150, 200)

        # Execute the effects
        log = f"{agent} uses {skill}"

        # 1. Handle Boss attacks
        if target == 'Boss':
            self.state['boss_hp'] = max(0, self.state['boss_hp'] - value)
            log += f" {agent} uses Fireball and attacks on Boss for {value} damage\n"

        # 2. Handle player targeting
        elif target in self.state['players']:
            max_hp = PLAYER_STATS[target]['hp']
            self.state['players'][target]['hp'] = min(
                    max_hp,
                    self.state['players'][target]['hp'] + value
                )
            log += f"{agent} uses Heal and heals on {target} for {value} healing.\n"

        self.turn_log.append(log)

    def boss_turn(self):
        """Boss attack logic with:
        - Taunt duration tracking
        - 50% damage reduction from shields
        """
        log = []
        damage = self.boss_damage
        taunting_player = self.state.get('aggro')
    
        if taunting_player and self.state['players'][taunting_player]['hp'] > 0:
          damage = damage // 2  
          self.state['players'][taunting_player]['hp'] = max(0, self.state['players'][taunting_player]['hp'] - damage)
          log.append(f"Boss focuses {taunting_player} for {damage} damage.\n")
        else:
            targets = sorted([p for p in self.state['players'] if self.state['players'][p]['hp'] > 0],
            key=lambda p: self.state['players'][p]['hp'])[:2]
            for target in targets:
              self.state['players'][target]['hp'] = max(0, self.state['players'][target]['hp'] - damage)
              log.append(f"Boss strikes {target} for {damage} damage.\n")
        self.state['aggro'] = None
        self.turn_log.append(log)
		
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

        # Build prompt sections
        prompt = f"""=== RAID BATTLE STATUS===

        [BOSS STATUS]
        - HP: {state['boss_hp']}/{MAX_BOSS_HP} ({boss_hp_percent:.1%})
        - Current Aggro: {state['aggro'] or "None"}

        [PARTY STATUS] ({alive_count}/4 alive)
        """
        # Add detailed player status
        for name in agents:
            player = state['players'][name]
            status = []

            # Health status
            if player['hp'] <= 0:
                status.append("DEAD")
            else:
                hp_percent = player['hp'] / player['max_hp']
                status.append(f" {player['hp']}/{player['max_hp']} ({hp_percent:.0%})")

                # Special statuses
                if state['aggro'] == name:
                    status.append(f"{name} AGGRO the Boss.")

            # Cooldowns
            cds = [f"{k}({v})" for k, v in self.cooldowns[name].items() if v > 0]

            prompt += f"""
            [{name.upper()}]
            - Status: {', '.join(status)}
            - Cooldowns: {', '.join(cds) if cds else 'None'}
            """

        # Add battle log
        # battle_log = '\n'.join(self.turn_log[-3:]) if self.turn_log else 'No actions recorded yet'
        # prompt += f"""
        #         [BATTLE LOG]
        #         {battle_log}
        #         """

        # Add detailed action spaces for each agent type
        prompt += f"""
            [RESPONSE INSTRUCTIONS]
            Each agent must respond with actions: {actions},
            based on their current status.
            """

        prompt += f"""
            The information of your round and the max round.
            MAX_round = {self.max_turn}
            Current round = {self.turn}
            """

        return prompt
