import argparse 
from simultaneous_game_agent import Agent, Game
from tqdm import tqdm
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='eacape_room')
    parser.add_argument('--max_negotiation_round', type=int, default=3)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--personality', type=str, default="rational")
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    parser.add_argument('--model', type=str, default='deepseek')
    args = parser.parse_args()


    result_save_dir = f'result/single_round/{args.model}/{args.game}_{args.personality}_negotiation_{args.max_negotiation_round}.json'

    args.system_prompt = f'You are a {args.personality} assistant that carefully answer the question.'
    decisions = []
    procedure = []
    for i in tqdm(range(args.sample_num)):
        game = Game(args)
        alice_action, bob_action = game.play()
        print(f'alice_action: {alice_action}')
        print(f'bob_action: {bob_action}')
        procedure.append(game.alice.previous_message)
        decisions.append({'Alice_action':alice_action, 'Bob_action':bob_action})

        with open(result_save_dir, 'w') as f:
            json.dump({'decisions':decisions, 'negotiation':procedure}, f, indent=4)


