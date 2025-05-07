from raid_agent import Agent, append_to_json, agents
from raid_env import BattleEngine
import os
import json
import argparse
from model import call_api
import numpy as np

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='raid')
    parser.add_argument('--max_negotiation_round', type=int, default=1)
    parser.add_argument('--final_round', type=int, default=1)
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--model', type=str, default='deepseek')
    parser.add_argument('--log_dir', default='game_theory_llm/log/3000_no_cot.json')
    args = parser.parse_args()
    engine = BattleEngine()
    args.system_prompt = f'You are a {args.system_prompt} assistant that carefully answer the question.'
    max_n = args.max_negotiation_round
    agents_chat = {'Agent1': Agent(args, 'Agent1', engine),
                   'Agent2': Agent(args, 'Agent2', engine),
                   'Agent3': Agent(args, 'Agent3', engine),
                   'Agent4': Agent(args, 'Agent4', engine)}
    # d = False
    # while not d:
    #     print('------------------------Negotiation begins-----------------------------')
    #     for i in range(0, max_n):
    #         for ag in agents:
    #             msg = agents_chat[ag].negotiation_2()
    #             agents_chat[ag].previous_message.append('{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + 'in game turn {}'.format(engine.turn) + msg)
    #             for oth in agents_chat[ag].the_other_player:
    #                 agents_chat[oth].previous_message.append(
    #                     '{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + 'in game turn {}'.format(engine.turn) + msg)
    #             formatted_msg = f"{ag} said in negotiation round {i + 1} in game turn {engine.turn}: {msg}."
    #             print(formatted_msg)
    #             append_to_json([formatted_msg], args.log_dir)
    #             if msg == '<s>halt negotiation</s>':
    #                 break
    #     print('------------------------Negotiation ends-----------------------------')
    #     actions = []
    #     for i in agents:
    #         actions.append(agents_chat[i].make_action())
    #     for ag in agents:
    #         agents_chat[ag].previous_message = []
    #     s, r, d, _ = engine.step(actions)
    #     append_to_json([engine.turn_log], args.log_dir)
    #     engine.print_state()
    #     if engine.is_over():
    #         print('------------------------ Fail to defeat boss.------------------------')
    #     if engine.state['boss_hp'] <= 0:
    #         print('----------------------------WIN----------------------')
    

    for i in range(0, args.final_round):
        print('------- Negotiation for the final team reward--------')
        for ag in agents:
            msg = agents_chat[ag].negotiation_2(s_q=True)
            agents_chat[ag].previous_message.append('{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + msg)
            for oth in agents_chat[ag].the_other_player:
                agents_chat[oth].previous_message.append(
                    '{}'.format(ag) + 'said in negotiation turn {}: '.format(i + 1) + msg)
            formatted_msg = f"{ag} said in negotiation turn {i + 1}: {msg}."
            print(formatted_msg)
            append_to_json([formatted_msg], args.log_dir)
    print('------- Final decision--------')
    msg = agents_chat[agents[0]].negotiation(pre=False, sum=True)
    formatted_msg = f"The final decision : {msg}."   
    print(formatted_msg)
    append_to_json([formatted_msg], args.log_dir)

    for ag in agents:
            agents_chat[ag].previous_message = []

    print(f'------------------log to {args.log_dir}--------------------')