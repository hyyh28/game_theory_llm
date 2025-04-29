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
        self.privious_thought = []
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
            7: "You must make decisions that adhere to the agreement, ensuring you maximize your rewards and minimize your payments as a self-interested agent in this negotiation.\n",
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
        while True:
            try:
                message, thought = self.generate_negotiation_message()
                message = parse(message)
                return message, thought
            except:
                time.sleep(0.1)

    def generate_negotiation_message(self):
        use_cot = self.args.use_cot
        negotiate_prompt = f"""
        ### Negotiation
        You can discuss with {self.the_other_player} to maximize the reward you can obtain. You have up to {self.max_negotiation_round} rounds to negotiate, and you must reach an agreement before exceeding this limit.
        Analyze the situation carefully and decide on what to say to the other player.
        
        You may offer a percentage (0–100%) of your own reward to the other player to influence their decision.
        You may also request a percentage (0–100%) of the other player's reward if helping them benefits you.
        If you feel the other player’s offer is unfair:
        - If the other player offers too little to you, you can **counter-offer a higher share**.
        - If the other player asks too much from you, you can **counter-offer a lower share**.
        
        You are self-interested, so your **goal** is to **maximize your own reward**:
        - You want to **pay as little as possible** to the other player.
        - You want to **receive as much as possible** from the other player.
        
        Surround your message with '<s>' and '</s>' to indicate the start and end of your message.
        
        You can also choose to halt the negotiation by saying '<s>halt negotiation</s>'.
        
        **Important: Once you agree to a proposal (or your proposal is agreed upon), you must not attempt to modify it further. In the next negotiation round, you should simply send '<s>halt negotiation</s>' to formally end the negotiation.**
        
        ---
        
        ### Important: Ensure Your Negotiation Is Actionable
        - Clearly assign which player chooses which action (no random decisions).
        - Clearly specify any reward transfer agreement.
        - Do not introduce randomness — everything must be explicitly decided.
        
        ---
        
        ### Negotiation Templates
        
        Proposing Cooperation:
        <s>
        Hi {self.the_other_player}, I propose that I will choose choice_1 and you will choose choice_2.
        Afterward, I will transfer XX% of my reward to you, so we both benefit.
        What do you think?
        </s>
        
        Agreeing (when accepting a plan):
        <s>
        Hi {self.the_other_player}, I agree to your plan. Let's proceed as proposed.
        </s>
        
        Counter-offer if unfair:
        <s>
        Hi {self.the_other_player}, I think your offer is not fully fair based on our contributions.
        I propose adjusting the reward transfer to XX% to make it more balanced. What do you think?
        </s>
        
        Ending (in the next round after agreement):
        <s>
        halt negotiation
        </s>

        """

        if use_cot:
            negotiate_prompt += """
            First, **analyze the current negotiation situation step-by-step based on Shapley Value principles**:
            
            - Step 1: What is the potential total reward if both players cooperate?
            - Step 2: Without detailed calculation, intuitively consider:
                - Think about what reward each agent can earn alone, without any help.
                - Think about how much extra reward each agent brings when it add to cooperation.
                - Identify which agents are more critical for achieving high rewards.
            - Step 3: According to Shapley Value thinking:
                - Each agent’s share should reflect their average marginal contribution across all cooperation orders.
                - Agents who consistently bring more extra reward should get a larger share.
                - Agents who add little value should not expect a large reward.
                - If a proposed deal gives you less than your fair share, prepare a counter-offer based on your contribution.
            - Step 4: Analyze the previous messages:
                - Does the other player recognize your contribution fairly?
                - Are they offering a fair split, or are they trying to exploit you?
            - Step 5: Based on fairness and self-interest:
                - Should you agree, propose a counteroffer, or challenge their fairness?
            
            Please **explicitly write down your reasoning under a section called "Thought Process:"**.
            
            ### Thought Process:
            (Write your analysis step-by-step following the above steps.)
            
            ---
            
            Then, **write your negotiation message separately**
            """

        negotiate_prompt += """
        Surround your message with '<s>' and '</s>' to indicate the start and end of your message. For example, '<s>Hi, how are you?</s>' or '<s>I will give you 30% of my reward if you choose action_X</s>'.
        You can also choose to halt the negotiation by saying 'halt negotiation'.
        """
        if self.previous_message:
            previous_messages = "\n\nThe previous rounds of negotiation are presented below:\n" + '\n'.join(
                self.previous_message)
            negotiate_prompt += previous_messages
        negotiate_prompt += self.game_setting

        message = call_api(self.args.model, negotiate_prompt, self.args.system_prompt)
        thought = None
        if use_cot:
            if "Thought Process:" in message:
                thought_part = message.split("Thought Process:")[1]
                if '<s>' in thought_part:
                    thought = thought_part.split('<s>')[0].strip()
                else:
                    thought = thought_part.strip()
        return message, thought

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
                alice_message, alice_thought = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice said in round {}: '.format(round + 1) + alice_message)
                self.bob.previous_message.append('Alice said in round {}: '.format(round + 1) + alice_message)
                if self.args.use_cot:
                    self.alice.privious_thought.append('Alice thought in round {}: '.format(round + 1) + alice_thought)
                    self.bob.privious_thought.append('Alice thought in round {}: '.format(round + 1) + alice_thought)

                bob_message, bob_thought = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob replied in round {}: '.format(round + 1) + bob_message)
                self.bob.previous_message.append('Bob replied in round {}: '.format(round + 1) + bob_message)
                if self.args.use_cot:
                    self.alice.privious_thought.append('Bob thought in round {}: '.format(round + 1) + bob_thought)
                    self.bob.privious_thought.append('Bob thought in round {}: '.format(round + 1) + bob_thought)
            else:
                bob_message, bob_thought = self.bob.negotiate()
                if bob_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Bob said in round {}: '.format(round + 1) + bob_message)
                self.bob.previous_message.append('Bob said in round {}: '.format(round + 1) + bob_message)
                if self.args.use_cot:
                    self.alice.privious_thought.append('Bob thought in round {}: '.format(round + 1) + bob_thought)
                    self.bob.privious_thought.append('Bob thought in round {}: '.format(round + 1) + bob_thought)

                alice_message, alice_thought = self.alice.negotiate()
                if alice_message == '<s>halt negotiation</s>':
                    break
                self.alice.previous_message.append('Alice replied in round {}: '.format(round + 1) + alice_message)
                self.bob.previous_message.append('Alice replied in round {}: '.format(round + 1) + alice_message)
                if self.args.use_cot:
                    self.alice.privious_thought.append('Alice thought in round {}: '.format(round + 1) + alice_thought)
                    self.bob.privious_thought.append('Alice thought in round {}: '.format(round + 1) + alice_thought)

        # 智能体选择动作
        alice_action = self.alice.make_action()
        bob_action = self.bob.make_action()

        # 解析让渡比例（假设消息中包含让渡比例，例如 "I will give you 30% of my reward if you choose action_X"）
        # alice_offer = self._extract_offer(self.alice.previous_message, 'Alice')
        # bob_offer = self._extract_offer(self.bob.previous_message, 'Bob')

        # 计算让渡后的实际收益
        # alice_final_payoff, bob_final_payoff = self.calculate_payoffs(alice_action, bob_action, alice_offer, bob_offer)

        return alice_action, bob_action

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
    parser.add_argument('--max_negotiation_round', type=int, default=3)
    parser.add_argument('--who_first', type=str, default='Alice')
    parser.add_argument('--sample_num', type=int, default=10)
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--prompt_for_negotiate', type=int, default=7)
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