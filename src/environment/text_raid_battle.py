import random

PLAYER_STATS = {
    'Warrior': {'hp': 800},
    'Mage1': {'hp': 400},
    'Mage2': {'hp': 400},
    'Priest': {'hp': 500},
}

MAX_BOSS_HP = 1500

class BattleEngine:
    def __init__(self, policy_dict):
        self.state = {
            'boss_hp': MAX_BOSS_HP,
            'aggro': None,
            'players': {
                name: {'hp': PLAYER_STATS[name]['hp'], 'shielded': False, 'max_hp': PLAYER_STATS[name]['hp']}
                for name in PLAYER_STATS
            }
        }
        self.cooldowns = {name: {} for name in PLAYER_STATS}
        self.policy_dict = policy_dict
        self.turn_log = []

    def is_over(self):
        if self.state['boss_hp'] <= 0:
            return True
        if all(p['hp'] <= 0 for p in self.state['players'].values()):
            return True
        return False

    def step(self):
        order = ['Warrior', 'Mage1', 'Mage2', 'Priest']
        for agent in order:
            if self.state['players'][agent]['hp'] <= 0:
                continue
            action = self.policy_dict[agent](agent, self.state, self.cooldowns)
            self.execute_action(agent, action)

        self.boss_turn()
        self.reduce_cooldowns()

    def execute_action(self, agent, action):
        skill = action.get("skill")
        target = action.get("target")
        value = action.get("value", 0)

        log = f"{agent} uses {skill}"
        if target == "Boss":
            self.state['boss_hp'] = max(0, self.state['boss_hp'] - value)
            log += f" on Boss for {value} dmg"
        elif target in self.state['players']:
            if skill in ["Heal", "Mass Heal"]:
                self.state['players'][target]['hp'] = min(
                    PLAYER_STATS[target]['hp'],
                    self.state['players'][target]['hp'] + value
                )
                log += f" on {target} for {value} HP"
        if skill == 'Taunt':
            self.state['aggro'] = agent
        if skill == 'Shield Block':
            self.state['players'][agent]['shielded'] = True

        self.cooldowns[agent][skill] = action.get("cooldown", 0)
        self.turn_log.append(log)

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
        - Threat Level: {"HIGH" if state['aggro'] != "Warrior" else "NORMAL"}

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
        - Position: {'Front' if name == 'Warrior' else 'Back'}
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
            4. Basic Attack (Deal 30-40 damage)

            [MAGE ACTIONS]
            1. Arcane Blast (Deal 150-180 damage, CD:3)
            2. Fireball (Deal 100-130 damage)
            3. Frostbolt (Deal 90-110 damage)
            4. Mana Shield (Convert mana to HP, CD:4)

            [PRIEST ACTIONS]
            1. Heal (Restore 150-200 HP to ally)
            2. Mass Heal (Restore 80-100 HP to all, CD:3)
            3. Smite (Deal 40-60 damage to boss)
            4. Divine Shield (Prevent 300 damage, CD:5)

            [RESPONSE INSTRUCTIONS]
            Each agent must respond with ONLY their action number (1-4)
            based on their role and current status.
            """

        return prompt



def fake_policy(agent, state, cooldowns):
    if agent == 'Warrior':
        if cooldowns[agent].get("Taunt", 0) == 0:
            return {"skill": "Taunt", "target": "Boss", "value": 0, "cooldown": 3}
        elif cooldowns[agent].get("Shield Block", 0) == 0 and state["players"][agent]["hp"] < 400:
            return {"skill": "Shield Block", "target": agent, "value": 0, "cooldown": 2}
        else:
            return {"skill": "Charge", "target": "Boss", "value": random.randint(50, 70), "cooldown": 0}

    elif "Mage" in agent:
        if cooldowns[agent].get("Arcane Blast", 0) == 0:
            return {"skill": "Arcane Blast", "target": "Boss", "value": random.randint(150, 180), "cooldown": 3}
        elif random.random() < 0.5:
            return {"skill": "Fireball", "target": "Boss", "value": random.randint(100, 130), "cooldown": 0}
        else:
            return {"skill": "Frostbolt", "target": "Boss", "value": random.randint(90, 110), "cooldown": 0}

    elif agent == "Priest":
        low_hp_players = sorted(
            [p for p in state["players"] if state["players"][p]["hp"] < state["players"][p]["max_hp"] * 0.6 and state["players"][p]["hp"] > 0],
            key=lambda p: state["players"][p]["hp"]
        )
        if cooldowns[agent].get("Mass Heal", 0) == 0 and len(low_hp_players) >= 2:
            return {"skill": "Mass Heal", "target": "All", "value": random.randint(80, 100), "cooldown": 3}
        elif low_hp_players:
            target = low_hp_players[0]
            return {"skill": "Heal", "target": target, "value": random.randint(150, 200), "cooldown": 0}
        else:
            return {"skill": "Idle", "target": None, "value": 0, "cooldown": 0}


if __name__ == "__main__":
    policy = {
        "Warrior": fake_policy,
        "Mage1": fake_policy,
        "Mage2": fake_policy,
        "Priest": fake_policy,
    }

    engine = BattleEngine(policy)
    while not engine.is_over():
        engine.step()
        engine.print_state()
