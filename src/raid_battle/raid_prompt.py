import random

def _create_system_message() -> str:
    skill_details = {
        'Taunt': {
            'effect': "Forces boss to attack you next turn (with 1/2 damage reduction)",
            'cooldown': 3,
            'reward': 0.5
        },
        'Fireball': {
            'effect': f"Deals {random.randint(100,150)} damage",
            'reward': 2.0
        },
        'Heal': {
            'effect': f"Restores {random.randint(150, 200)} HP to the player with lowest HP",
            'reward': 0.5
        }
    }

    # Build skill descriptions
    skill_descriptions = []
    for skill, params in skill_details.items():
        desc = f"{skill}: {params['effect']}"
        if 'cooldown' in params:
            desc += f" (Cooldown: {params['cooldown']} turns)"
        desc += f" - Reward: {params['reward']} pts"
        skill_descriptions.append(desc)
    
    skills_str = '\n'.join(f'• {desc}' for desc in skill_descriptions)

    prompt = f"""### Raid Battle System (All Players Identical)
    

    **Available Skills**:
    {skills_str}

    **Battle Rules**:
    Boss damage: 200.
    1. Taunt lasts 1 turn (with automatic 50% damage reduction). Remember, the boss can be only taunted by one agent everytime!
    2. Boss attacks taunter or 2 lowest-HP players.
    3. 10-round time limit

    **Reward Distribution**:
    - Individual reward: Action reward
      r_tot = 100 * (1- the percentage of dead agent - total turn/max_turn)
    - Team reward: r_tot (win) / -100 (loss). Default: Equal split among each player. Custom: Negotiate alternative splits via chat.
    - Total reward for one player: The sum of team and individual reward.

    **Key Strategies**:
    - Coordinate taunt rotations
    - Balance damage and healing
    - Monitor remaining rounds
    """
    return prompt