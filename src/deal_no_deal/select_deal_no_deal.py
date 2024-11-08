import argparse
from tqdm import tqdm
from deal_no_deal_metrics import check_human_pareto_optimal_envy_free, process_data, check_envy_free, check_pareto_optimalities
import random 
import sys 

def L1_selection(data):
    def maximum_covered(example_count, agent1_values, agent2_values):
        r1 = False
        r2 = False
        agent_1_max_value = max(agent1_values)
        agent_1_max_value_item = agent1_values.index(agent_1_max_value)
        if sum([example_count[i]*agent1_values[i] for i in range(3) if i != agent_1_max_value_item]) >= agent_1_max_value:
            r1 = True
        agent_2_max_value = max(agent2_values)
        agent_2_max_value_item = agent2_values.index(agent_2_max_value)
        if sum([example_count[i]*agent2_values[i] for i in range(3) if i != agent_2_max_value_item]) >= agent_2_max_value:
            r2 = True
        if r1 and r2 and agent_1_max_value_item == agent_2_max_value_item:
            return True
        return False
    data_difficulty = {}
    checked_setting = []
    for i, one_data in enumerate(data):
        example_count, agent1_values, agent1_values_text, agent2_values, agent2_values_text, agent1_human_outcomes, agent2_human_outcomes = process_data(one_data)
        if (example_count, agent1_values_text, agent2_values_text) in checked_setting:
            # remove repetition
            L1_distance = 100
        elif example_count[0]%2 == 0 and example_count[1]%2 == 0 and example_count[2]%2 == 0:
            # remove very easy envy-free cases
            L1_distance = 100
        elif maximum_covered(example_count, agent1_values, agent2_values):
            # remove case where the maximum valued item can be covered by the other two items
            L1_distance = 100
        else:
            L1_distance = sum([abs(agent1_values[i] - agent2_values[i]) for i in range(3)])
            checked_setting.append((example_count, agent1_values_text, agent2_values_text))
        data_difficulty[i] = L1_distance
    return data_difficulty

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deal or No Deal')
    parser.add_argument('--data', type=str, default='deal_no_deal_test.txt', help='Path to the data file')
    parser.add_argument('--system_prompt', type=str, default="rational")
    parser.add_argument('--max_negotiation_round', type=int, default=20)
    parser.add_argument('--datapoint_id', type=int, default=0)
    parser.add_argument('--special_prompting', action='store_true')
    parser.add_argument('--use_workflow', action='store_true')
    parser.add_argument('--model', type=str, default='sonnet', help='sonnet, opus, gpt-4o, gpt-o1')
    parser.add_argument('--distance', type=int, default=2, help='L1, L2')
    args = parser.parse_args()

    with open(args.data, 'r') as f:
        data = f.readlines()
    # remove repetitive lines
    data = [d for i,d in enumerate(data) if i % 2 == 0]
    print(f'Number of original dataset datapoint: {len(data)}')
    not_pareto_optimal_envy_free_human_choices = []
    for d in data:
        if not check_human_pareto_optimal_envy_free(d):
            not_pareto_optimal_envy_free_human_choices.append(d)
    total_number = len(data)
    min_hard_percentage = 1 - len(not_pareto_optimal_envy_free_human_choices)/total_number
    print(f'Original dataset: Number of data where human choices are not pareto optimal envy free: {len(not_pareto_optimal_envy_free_human_choices)}')
    print(f'Original dataset: Percentage of Pareto optimal envy free data: {min_hard_percentage}')
    
    #### find 50 different difficulty datapoints
    data_difficulty = L1_selection(data)
    print(len(data))

    selected_data = [data[i] for i in list(data_difficulty.keys()) if data_difficulty[i] <= args.distance]
    envy_free = []
    pareto_optimal = []
    pareto_optimal_envy_free_human_choices = []
    not_agreement = []
    for d in selected_data:
        example_count, agent1_values, agent1_values_text, agent2_values, agent2_values_text, agent1_human_outcomes, agent2_human_outcomes = process_data(d)
        try:
            if check_envy_free(agent1_human_outcomes, agent2_human_outcomes, d):
                envy_free.append(d)
            if check_pareto_optimalities(agent1_human_outcomes, agent1_values, agent2_human_outcomes, agent2_values, example_count):
                pareto_optimal.append(d)
            if check_human_pareto_optimal_envy_free(d):
                pareto_optimal_envy_free_human_choices.append(d)
        except:
            not_agreement.append(d)


    total_number = len(selected_data)
    envy_free_percentage = len(envy_free)/total_number
    pareto_optimal_percentage = len(pareto_optimal)/total_number
    both_percentage = len(pareto_optimal_envy_free_human_choices)/total_number
    agreement_percentage = 1- len(not_agreement)/total_number
    print(f'Total selected number of data: {total_number}')
    print(f"Percentage of agreement data: {agreement_percentage}")
    print(f'Percentage of envy-free data : {envy_free_percentage}')
    print(f'Percentage of pareto-optimal data: {pareto_optimal_percentage}')
    print(f'Percentage of both pareto-optimal and envy-free data: {both_percentage}')

    # with open('sampled_50_deal_no_deal.txt', 'w') as f:
    #     for d in selected_data:
    #         f.write(d)
    # print('saved sampled_50_deal_no_deal.txt')
