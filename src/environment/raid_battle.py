import itertools
import random
import pygame
import sys
import time

# ==== Game Constants ====
MAX_BOSS_HP = 1000
PLAYER_STATS = {
    'Warrior': {'hp': 800},
    'Mage1': {'hp': 400},
    'Mage2': {'hp': 400},
    'Priest': {'hp': 500},
}

# ==== Visualization Settings ====
WIDTH, HEIGHT = 800, 600
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
ORANGE = (255, 165, 0)
PURPLE = (160, 32, 240)
CYAN = (0, 255, 255)
FONT = None
ANIMATION_DURATION = 30

AVATAR_RADIUS = 15
AVATAR_X = 70
AVATAR_Y_BASE = 130

# ==== Load Images ====
def load_images():
    global background_img, warrior_img, mage1_img, mage2_img, priest_img, boss_img
    background_img = pygame.image.load('background.png')
    warrior_img = pygame.image.load('warrior.png')
    mage1_img = pygame.image.load('mage1.png')
    mage2_img = pygame.image.load('mage2.png')
    priest_img = pygame.image.load('priest.png')
    boss_img = pygame.image.load('boss.png')

# ==== Utility Drawing ====
def draw_bar(surface, x, y, w, h, ratio, color):
    pygame.draw.rect(surface, BLACK, (x, y, w, h))
    pygame.draw.rect(surface, color, (x, y, int(w * ratio), h))

def draw_projectile(surface, start, end, color, shape='line'):
    for i in range(ANIMATION_DURATION):
        screen.fill(WHITE)
        draw_background_and_static()
        intermediate_x = int(start[0] + (end[0] - start[0]) * i / ANIMATION_DURATION)
        intermediate_y = int(start[1] + (end[1] - start[1]) * i / ANIMATION_DURATION)

        if shape == 'circle':
            pygame.draw.circle(surface, color, (intermediate_x, intermediate_y), 8)
        else:
            pygame.draw.line(surface, color, start, (intermediate_x, intermediate_y), 4)

        pygame.display.flip()
        pygame.time.delay(10)


def float_text(surface, text, pos, color=WHITE):
    for i in range(20):
        draw_background_and_static()
        y_offset = pos[1] - i * 2
        txt = FONT.render(text, True, color)
        screen.blit(txt, (pos[0], y_offset))
        pygame.display.flip()
        pygame.time.delay(20)

def draw_avatar(surface, index, color, img):
    y = AVATAR_Y_BASE + index * 60
    img = pygame.transform.scale(img, (AVATAR_RADIUS * 2, AVATAR_RADIUS * 2))
    surface.blit(img, (AVATAR_X - AVATAR_RADIUS, y - AVATAR_RADIUS))


def draw_background_and_static():
    screen.blit(pygame.transform.scale(background_img, (WIDTH, HEIGHT)), (0, 0))

    # ==== Draw Boss ====
    boss_pos = (WIDTH // 2 - 60, 50)
    boss_img_scaled = pygame.transform.scale(boss_img, (120, 120))
    screen.blit(boss_img_scaled, boss_pos)

    # Draw boss HP bar (small)
    bar_width = 120
    hp_ratio = current_boss_hp / MAX_BOSS_HP
    draw_bar(screen, boss_pos[0], boss_pos[1] - 15, bar_width, 10, hp_ratio, RED)

    # ==== Draw Heroes ====
    spacing = WIDTH // 5
    for i, name in enumerate(current_state['players']):
        x = spacing * (i + 1) - 40
        y = HEIGHT - 120
        img = get_avatar_img(name)
        img_scaled = pygame.transform.scale(img, (80, 80))
        screen.blit(img_scaled, (x, y))

        # Small HP bar on top
        hp = current_state['players'][name]['hp']
        max_hp = PLAYER_STATS[name]['hp']
        draw_bar(screen, x, y - 12, 80, 8, max(0, hp) / max_hp, GREEN)

        # Draw name centered under the avatar
        name_surface = FONT.render(name, True, WHITE)
        name_rect = name_surface.get_rect(center=(x + 40, y + 90))
        screen.blit(name_surface, name_rect)

        # Save avatar center for effect rendering
        current_state['players'][name]['pos'] = (x + 40, y + 40)



def get_avatar_img(name):
    if name == 'Warrior':
        return warrior_img
    elif name == 'Mage1':
        return mage1_img
    elif name == 'Mage2':
        return mage2_img
    elif name == 'Priest':
        return priest_img
    return None


# ==== Simple Agent Logic ====
def warrior_action(state, cooldowns):
    warrior = state['players']['Warrior']
    if cooldowns['Warrior'].get('Shield Block', 0) == 0 and warrior['hp'] < 300:
        cooldowns['Warrior']['Shield Block'] = 2
        warrior['shielded'] = True
        return 'Shield Block', 0
    elif cooldowns['Warrior'].get('Taunt', 0) == 0:
        cooldowns['Warrior']['Taunt'] = 3
        state['aggro'] = 'Warrior'
        return 'Taunt', 0
    else:
        return 'Charge', random.randint(50, 70)

def mage_action(state, name, cooldowns):
    if cooldowns[name].get('Arcane Blast', 0) == 0:
        cooldowns[name]['Arcane Blast'] = 3
        return 'Arcane Blast', random.randint(150, 180)
    elif random.random() < 0.5:
        return 'Fireball', random.randint(100, 130)
    else:
        return 'Frostbolt', random.randint(90, 110)

def priest_action(state, cooldowns):
    priest = state['players']['Priest']
    low_hp = [p for p in state['players'] if state['players'][p]['hp'] < PLAYER_STATS[p]['hp'] * 0.6 and state['players'][p]['hp'] > 0]
    if cooldowns['Priest'].get('Mass Heal', 0) == 0 and len(low_hp) >= 2:
        cooldowns['Priest']['Mass Heal'] = 3
        treat = random.randint(80, 100)
        for p in state['players']:
            if state['players'][p]['hp'] > 0:
                state['players'][p]['hp'] = min(PLAYER_STATS[p]['hp'], state['players'][p]['hp'] + treat)
        return 'Mass Heal', 0, treat
    elif low_hp:
        treat = random.randint(150, 200)
        target = low_hp[0]
        state['players'][target]['hp'] = min(PLAYER_STATS[target]['hp'], state['players'][target]['hp'] + treat)
        return 'Heal', target, treat
    return 'Idle', 0, 0

def show_skill_text(name, skill):
    x, y = current_state['players'][name]['pos']
    txt = FONT.render(skill, True, WHITE)
    for i in range(20):
        draw_background_and_static()
        screen.blit(txt, (x + 20, y - 30 - i))
        pygame.display.flip()
        pygame.time.delay(20)

# ==== Game Simulator with Enhanced Boss Skills ====
def run_visual_game(active_agents):
    global screen, FONT, current_state, current_boss_hp
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("LLM Raid Simulation")
    FONT = pygame.font.SysFont('Arial', 20)

    load_images()

    boss_hp = MAX_BOSS_HP
    current_state = {
        'boss_hp': boss_hp,
        'aggro': None,
        'players': {k: {'hp': PLAYER_STATS[k]['hp'], 'shielded': False} for k in active_agents}
    }
    current_boss_hp = boss_hp
    cooldowns = {k: {} for k in active_agents}
    turns = 0
    clock = pygame.time.Clock()
    boss_pos = (WIDTH // 2 + 60, 110)

    while boss_hp > 0 and any(p['hp'] > 0 for p in current_state['players'].values()):
        turns += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        draw_background_and_static()

        # ==== Boss action ====
        if current_state['aggro'] != 'Warrior':
            low_hp_players = sorted(
                [p for p in current_state['players'] if current_state['players'][p]['hp'] > 0],
                key=lambda p: current_state['players'][p]['hp']
            )[:2]
            for player in low_hp_players:
                dmg = 300
                current_state['players'][player]['hp'] -= dmg
                end_pos = current_state['players'][player]['pos']
                draw_projectile(screen, boss_pos, end_pos, RED, 'circle')
                float_text(screen, f"-{dmg}", end_pos)
        else:
            for player in current_state['players']:
                if current_state['players'][player]['hp'] > 0:
                    dmg = 100
                    current_state['players'][player]['hp'] -= dmg
                    end_pos = current_state['players'][player]['pos']
                    draw_projectile(screen, boss_pos, end_pos, RED, 'circle')
                    float_text(screen, f"-{dmg}", end_pos)

        # ==== Players action ====
        log = []
        for agent in active_agents:
            if current_state['players'][agent]['hp'] <= 0:
                continue

            start_pos = current_state['players'][agent]['pos']
            if agent == 'Warrior':
                skill, effect = warrior_action(current_state, cooldowns)
                if skill == 'Charge':
                    draw_projectile(screen, start_pos, boss_pos, RED)
                    boss_hp -= effect
                    float_text(screen, f"-{effect}", boss_pos)
                log.append(f"{agent} used {skill}")

            elif 'Mage' in agent:
                skill, dmg = mage_action(current_state, agent, cooldowns)
                color = RED
                draw_projectile(screen, start_pos, boss_pos, color, 'circle')
                boss_hp -= dmg
                float_text(screen, f"-{dmg}", boss_pos)
                log.append(f"{agent} used {skill}")

            elif agent == 'Priest':
                skill, target, treat = priest_action(current_state, cooldowns)
                if skill == 'Heal':
                    end_pos = current_state['players'][target]['pos']
                    draw_projectile(screen, start_pos, end_pos, GREEN, 'circle')
                    float_text(screen, f"+{treat}", end_pos)
                elif skill == 'Mass Heal':
                    for target_name in current_state['players']:
                        if current_state['players'][target_name]['hp'] > 0:
                            end_pos = current_state['players'][target_name]['pos']
                            draw_projectile(screen, start_pos, end_pos, GREEN, 'circle')
                            float_text(screen, f"+{treat}", end_pos)
                log.append(f"{agent} used {skill}")

            show_skill_text(agent, skill)

        # Cooldown reduction
        for a in cooldowns:
            for skill in list(cooldowns[a].keys()):
                if cooldowns[a][skill] > 0:
                    cooldowns[a][skill] -= 1

        current_boss_hp = boss_hp

        draw_background_and_static()
        for i, line in enumerate(log):
            screen.blit(FONT.render(line, True, WHITE), (450, 120 + i * 30))

        pygame.display.flip()
        clock.tick(1)

    time.sleep(2)
    pygame.quit()

if __name__== "__main__":
    run_visual_game(['Warrior', 'Mage1', 'Mage2', 'Priest'])
