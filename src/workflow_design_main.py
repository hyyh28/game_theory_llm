import argparse 
from workflow_design import Sequential_Game, Simultaneous_Game
from tqdm import tqdm
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='draco', help="prisoner_dilemma, battle_of_sexes, stag_hunt_small, rock_paper_scissors, IESDS, imbalanced_actions, duopolistic_competition, escalation_game, monopoly_game, draco, trigame, hot_cold_game")
    parser.add_argument('--game_type', type=str, default='simultaneous', help="simultaneous or sequential")
    parser.add_argument('--max_negotiation_round', type=int, default=0)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--personality', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    parser.add_argument('--model', type=str, default='sonnet')  
    args = parser.parse_args()

    result_save_dir = f'result/workflow/{args.model}/{args.game}_negotiation_{args.max_negotiation_round}.json'

    args.system_prompt = f'You are a {args.personality} assistant that carefully answer the question.'
    
    if args.game_type == 'simultaneous':
        decisions = []
        procedure = []
        strategies = []
        for i in tqdm(range(args.sample_num)):
            game = Simultaneous_Game(args)
            alice_action, bob_action = game.play()
            print(f'alice_action: {alice_action}')
            print(f'bob_action: {bob_action}')
            procedure.append(game.alice.previous_message)
            decisions.append({'Alice_action':alice_action, 'Bob_action':bob_action})
            strategies.append({'Alice_strategy':game.alice.strategy_summary, 'Bob_strategy':game.bob.strategy_summary})

            with open(result_save_dir, 'w') as f:
                json.dump({'decisions':decisions, 'negotiation':procedure, 'strategies':strategies}, f, indent=4)
    else:
        decisions = []
        procedure = []
        strategies = []
        for i in tqdm(range(args.sample_num)):
            game = Sequential_Game(args)
            action_sequence = game.play()
            print(f'action_sequence: {action_sequence}')
            procedure.append(game.alice.previous_message)
            decisions.append(action_sequence)
            strategies.append({'Alice_strategy':game.alice.strategy_summary, 'Bob_strategy':game.bob.strategy_summary})

            with open(result_save_dir, 'w') as f:
                json.dump({'decisions':decisions, 'negotiation':procedure, 'strategies':strategies}, f, indent=4)