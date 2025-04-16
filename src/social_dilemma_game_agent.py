from model import call_api
import argparse
from configuration import payoff_matrix
import time
from tqdm import tqdm
import json

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

class Agent:
    def __init__(self, args, name):
        self.args = args
        self.name = name
        self.the_other_player = 'Bob' if self.name == 'Alice' else 'Alice'
        self.max_negotiation_round = self.args.max_negotiation_round
        self.previous_message = []
        # game setting
        self.actions = list(payoff_matrix[self.args.game][self.name].keys())
        action_number = len(self.actions)
        self.action_names = ', '.join(self.actions)
        rule_descriptions = self.create_rule_description()
        self.game_setting = f"""
### Game Introduction
You are playing a one-round game with another player to maximize the reward you can obtain. This game involves two players, Alice and Bob.
You are playing as {self.name}. You have {action_number} choices: {self.action_names}.
The other player, {self.the_other_player}, also has {action_number} choices: {self.action_names}.
### Game Rules
{rule_descriptions}
"""
        self.prompt_for_negotiate = {
            0: '',
            1: "Please carefully analyze the negotiation messages, think about whether you can trust {} message, and make your own decision.\n",
            2: "Please carefully analyze the negotiation messages and make your own decision.\n",
            3: "You can choose your own choice regardless what {} says.\n",
            4: "You should make your own choice regardless what {} says.\n",
            5: "You must make your own choice regardless what {} says.\n",
            6: "Carefully analyze and think about whether you can trust {} message, and then make your own decision.\n",
        }

    def create_rule_description(self):
        sentences = []
        for choice_1 in self.actions:
            for choice_2 in self.actions:
                player_1_payoff = payoff_matrix[self.args.game][self.name][choice_1][
                    self.the_other_player + "_" + choice_2]
                player_2_payoff = payoff_matrix[self.args.game][self.the_other_player][choice_2][
                    self.name + "_" + choice_1]
                if choice_1 == choice_2:
                    r = f"- If both you and {self.the_other_player} choose {choice_1}, you will receive a reward of {player_1_payoff} and {self.the_other_player} will receive a reward of {player_2_payoff}."
                    sentences.append(r)
                elif choice_1 != choice_2:
                    r = f"- If you choose {choice_1} while {self.the_other_player} chooses {choice_2}, you will receive a reward of {player_1_payoff} and {self.the_other_player} will receive a reward of {player_2_payoff}."
                    sentences.append(r)
            sentences.append('\n')
        return '\n'.join(sentences)

    def make_action(self):
        action_prompt = f"""
### Your Action
Analyse the problem and the negotiation message if there is any.
Please choose one of the following actions to maximize your reward.
Surround your choice with '<s>' and '</s>' to indicate the start and end of your choice. For example, '<s>choice_1</s>', '<s>choice_2</s>', '<s>choice_3</s>'.
Action choices: {self.action_names}
"""
        if self.previous_message:
            previous_messages = "\n### Negotiation Messages\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            action_prompt = previous_messages + '\n' + action_prompt
            action_prompt = action_prompt + '\n\n' + self.prompt_for_negotiate[self.args.prompt_for_negotiate].format(
                self.the_other_player)
        action_prompt = self.game_setting + '\n' + action_prompt
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

    def negotiate(self):
        negotiate_prompt = f"""
### Negotiation
You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have a maximum of {self.max_negotiation_round} rounds to negotiate.
Analyze the situation and decide on what to say to the other player. You can offer a percentage of your reward (0-100%) to influence the other player's decision.
Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>' or '<s>I will give you 30% of my reward if you choose action_X</s>'.
You can also choose to halt the negotiation by saying 'halt negotiation'.
"""
        if self.previous_message:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt = self.game_setting + negotiate_prompt
        while True:
            try:
                message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
                message = parse(message)
                return message
            except:
                time.sleep(0.1)

class Game:
    def __init__(self, args):
        self.args = args
        self.alice = Agent(args, 'Alice')
        self.bob = Agent(args, 'Bob')

    def calculate_payoffs(self, alice_action, bob_action, alice_offer=0, bob_offer=0):
        """
        计算让渡利益后的实际收益。
        :param alice_action: Alice 选择的动作
        :param bob_action: Bob 选择的动作
        :param alice_offer: Alice 让渡给 Bob 的收益比例（0-100%）
        :param bob_offer: Bob 让渡给 Alice 的收益比例（0-100%）
        :return: 让渡后的 Alice 和 Bob 的实际收益
        """
        # 获取原始收益
        alice_payoff = payoff_matrix[self.args.game]['Alice'][alice_action][f'Bob_{bob_action}']
        bob_payoff = payoff_matrix[self.args.game]['Bob'][bob_action][f'Alice_{alice_action}']

        # 计算让渡后的收益
        alice_final_payoff = alice_payoff * (1 - alice_offer / 100) + bob_payoff * (bob_offer / 100)
        bob_final_payoff = bob_payoff * (1 - bob_offer / 100) + alice_payoff * (alice_offer / 100)

        return alice_final_payoff, bob_final_payoff

    def play(self):
        for round in range(self.args.max_negotiation_round):
            if self.args.who_first == 'Alice':
                alice_message = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice said in round {}: '.format(round + 1) + alice_message)
                self.bob.previous_message.append('Alice said in round {}: '.format(round + 1) + alice_message)

                bob_message = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob replied in round {}: '.format(round + 1) + bob_message)
                self.bob.previous_message.append('Bob replied in round {}: '.format(round + 1) + bob_message)
            else:
                bob_message = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob said in round {}: '.format(round + 1) + bob_message)
                self.bob.previous_message.append('Bob said in round {}: '.format(round + 1) + bob_message)

                alice_message = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice replied in round {}: '.format(round + 1) + alice_message)
                self.bob.previous_message.append('Alice replied in round {}: '.format(round + 1) + alice_message)

        # 智能体选择动作
        alice_action = self.alice.make_action()
        bob_action = self.bob.make_action()

        # 解析让渡比例（假设消息中包含让渡比例，例如 "I will give you 30% of my reward if you choose action_X"）
        alice_offer = self._extract_offer(self.alice.previous_message, 'Alice')
        bob_offer = self._extract_offer(self.bob.previous_message, 'Bob')

        # 计算让渡后的实际收益
        alice_final_payoff, bob_final_payoff = self.calculate_payoffs(alice_action, bob_action, alice_offer, bob_offer)

        return alice_action, bob_action, alice_offer, bob_offer, alice_final_payoff, bob_final_payoff

    def _extract_offer(self, messages, agent_name):
        """
        从谈判消息中解析让渡比例。
        :param messages: 谈判消息列表
        :param agent_name: 智能体名称（Alice 或 Bob）
        :return: 让渡比例（0-100）
        """
        for message in messages:
            if f"{agent_name} said" in message:
                if "give you" in message and "%" in message:
                    # 提取让渡比例（例如 "I will give you 30% of my reward"）
                    offer = message.split("give you")[1].split("%")[0].strip()
                    return int(offer)
        return 0  # 默认无让渡

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=str, default='prisoner_dilemma',
                        help="prisoner_dilemma, battle_of_sexes, stag_hunt, rock_paper_scissors")
    parser.add_argument('--max_negotiation_round', type=int, default=0)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=0)
    args = parser.parse_args()
    # alice_action, bob_action = game.play()
    # print(f'alice_action: {alice_action}')
    # print(f'bob_action: {bob_action}')
    result_save_dir = f'result/single_round/{args.game}_{args.max_negotiation_round}_{args.who_first}_first_{args.system_prompt}_negotationpromptnumber_{args.prompt_for_negotiate}.json'
    args.system_prompt = f'You are a {args.system_prompt} assistant that carefully answer the question.'
    decisions = []
    procedure = []
    for i in tqdm(range(args.sample_num)):
        game = Game(args)
        alice_action, bob_action = game.play()
        print(f'alice_action: {alice_action}')
        print(f'bob_action: {bob_action}')
        procedure.append(game.alice.previous_message)
        decisions.append({'Alice_action': alice_action, 'Bob_action': bob_action})
        # with open(result_save_dir, 'w') as f:
        #     json.dump({'decisions':decisions, 'negotiation':procedure}, f, indent=4)