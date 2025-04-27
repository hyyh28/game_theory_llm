import argparse
from social_dilemma_game_agent import Agent, Game
from tqdm import tqdm
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='eacape_room')
    parser.add_argument('--max_negotiation_round', type=int, default=3)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--personality', type=str, default="rational")
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--prompt_for_negotiate', type=int, default=7)
    parser.add_argument('--model', type=str, default='deepseek')
    args = parser.parse_args()


    result_save_dir = f'result/single_round/{args.model}/{args.game}_{args.personality}_negotiation_{args.max_negotiation_round}.json'

    args.system_prompt = f'You are a {args.personality} assistant that carefully answer the question.'
    decisions = []
    procedure = []
    for i in tqdm(range(args.sample_num)):
        game = Game(args)
        alice_action, bob_action, alice_offer, bob_offer, alice_final_payoff, bob_final_payoff = game.play()
        # 打印结果
        print(f"Alice chose: {alice_action}, Bob chose: {bob_action}")
        print(f"Alice offered {alice_offer}% of her reward to Bob.")
        print(f"Bob offered {bob_offer}% of his reward to Alice.")
        print(f"Alice's final payoff: {alice_final_payoff}")
        print(f"Bob's final payoff: {bob_final_payoff}")
        procedure.append(game.alice.previous_message)
        decisions.append({'Alice_action':alice_action, 'Bob_action':bob_action})

        with open(result_save_dir, 'w') as f:
            json.dump({'decisions':decisions, 'negotiation':procedure}, f, indent=4)


