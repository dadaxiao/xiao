def custom_p_e_m(cand_ent_num=15, allowed_entities_set=None,
                 lowercase_p_e_m=False):
    """Args:
    cand_ent_num: how many candidate entities to keep for each mention
    allowed_entities_set: restrict the candidate entities to only this set. for example
    the most frequent 1M entities. First this restiction applies and then the cand_ent_num."""
    wall_start = time.time()
    # 存储实体提及m链接到实体e的概率
    p_e_m = dict()  # for each mention we have a list of tuples (ent_id, score)
    # mention_total_freq为全部实体提及出现的频率
    mention_total_freq = dict()   # for each mention of the p_e_m we store the total freq
                                # this will help us decide which cand entities to take
    p_e_m_errors = 0
    entityNameIdMap = EntityNameIdMap()
    entityNameIdMap.init_compatible_ent_id()
    incompatible_ent_ids = 0
    with open(config.base_folder + 'data/basic_data/prob_yago_crosswikis_wikipedia_p_e_m.txt') as fin:
        duplicate_mentions_cnt = 0
        clear_conflict_winner = 0  # both higher absolute frequency and longer cand list
        not_clear_conflict_winner = 0  # higher absolute freq but shorter cand list
        for line in fin:
            line = line.rstrip()
            try:
                temp = line.split("\t")
                mention, entities = temp[0],  temp[2:]
                absolute_freq = int(temp[1])
                res = []
                for e in entities:
                    if len(res) >= cand_ent_num:
                        break
                    ent_id, score, _ = map(str.strip, e.split(',', 2))
                    #print(ent_id, score)
                    if not entityNameIdMap.is_valid_entity_id(ent_id):
                        incompatible_ent_ids += 1
                    elif allowed_entities_set is not None and \
                                    ent_id not in allowed_entities_set:
                        pass
                    else:
                        res.append((ent_id, float(score)))
                if res:
                    if mention in p_e_m:
                        duplicate_mentions_cnt += 1
                        #print("duplicate mention: ", mention)
                        if absolute_freq > mention_total_freq[mention]:
                            if len(res) > len(p_e_m[mention]):
                                clear_conflict_winner += 1
                            else:
                                not_clear_conflict_winner += 1
                            p_e_m[mention] = res
                            mention_total_freq[mention] = absolute_freq
                    else:
                        p_e_m[mention] = res    # for each mention we have a list of tuples (ent_id, score)
                        mention_total_freq[mention] = absolute_freq

            except Exception as esd:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(exc_type, fname, exc_tb.tb_lineno)
                p_e_m_errors += 1
                print("error in line: ", repr(line))

    print("duplicate_mentions_cnt: ", duplicate_mentions_cnt)
    print("end of p_e_m reading. wall time:", (time.time() - wall_start)/60, " minutes")
    print("p_e_m_errors: ", p_e_m_errors)
    print("incompatible_ent_ids: ", incompatible_ent_ids)

    if not lowercase_p_e_m:   # do not build lowercase dictionary
        return p_e_m, None, mention_total_freq

    wall_start = time.time()
    # two different p(e|m) mentions can be the same after lower() so we merge the two candidate
    # entities lists. But the two lists can have the same candidate entity with different score
    # we keep the highest score. For example if "Obama" mention gives 0.9 to entity Obama and
    # OBAMA gives 0.7 then we keep the 0.9 . Also we keep as before only the cand_ent_num entities
    # with the highest score
    p_e_m_lowercased = defaultdict(lambda: defaultdict(int))

    for mention, res in p_e_m.items():
        l_mention = mention.lower()
        # if l_mention != mention and l_mention not in p_e_m:
        #   the same so do nothing      already exist in dictionary
        #   e.g. p(e|m) has Obama and obama. So when i convert Obama to lowercase
        # I find that obama already exist so i will prefer this.
        if l_mention not in p_e_m:
            for r in res:
                ent_id, score = r
                p_e_m_lowercased[l_mention][ent_id] = max(score, p_e_m_lowercased[l_mention][ent_id])

    print("end of p_e_m lowercase. wall time:", (time.time() - wall_start)/60, " minutes")

    import operator
    p_e_m_lowercased_trim = dict()
    for mention, ent_score_map in p_e_m_lowercased.items():
        sorted_ = sorted(ent_score_map.items(), key=operator.itemgetter(1), reverse=True)
        p_e_m_lowercased_trim[mention] = sorted_[:cand_ent_num]

    return p_e_m, p_e_m_lowercased_trim, mention_total_freq