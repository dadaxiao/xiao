# b9d87f7  on Mar 21 Nikolaos Kolitsas ffnn dropout and some minor modif in evaluate to accept entity extension
# ed_model_21_march
import pickle

import numpy as np
import tensorflow as tf

# import model.config as config
import config
# import model.util as util
import util
# from .base_model import BaseModel
from base_model import BaseModel


class Model(BaseModel):

    def __init__(self, args, next_element):
        super().__init__(args)
        # 把传入的next_element的各个东西分别赋值给各个属性变量
        self.chunk_id, self.words, self.words_len, self.chars, self.chars_len, \
        self.begin_span, self.end_span, self.spans_len, \
        self.cand_entities, self.cand_entities_scores, self.cand_entities_labels, self.cand_first_paragraph, \
        self.cand_entities_len, self.ground_truth, self.ground_truth_len, \
        self.begin_gm, self.end_gm = next_element

        self.begin_span = tf.cast(self.begin_span, tf.int32)
        self.end_span = tf.cast(self.end_span, tf.int32)
        self.words_len = tf.cast(self.words_len, tf.int32)
        """
        self.words:list,单词对应的id,  tf.int64, shape=[None, None]   # shape = (batch size, max length of sentence in batch)
        self.words_len:int, 某句话的单词数量, tf.int32, shape=[None],     #   shape = (batch size)
        self.chars: [[],[]],存储的是每个单词对应的字符的ID, tf.int64, shape=[None, None, None], # shape = (batch size, max length of sentence, max length of word)
        self.chars_len: list，存每个单词字符数量,tf.int64, shape=[None, None],   # shape = (batch_size, max_length of sentence)
        self.begin_span: tf.int32, shape=[None, None],  # shape = (batch_size, max number of candidate spans in one of the batch sentences)
        self.end_span: tf.int32, shape=[None, None],
        self.spans_len: tf.int64, shape=[None],     # shape = (batch size)
        self.cand_entities: tf.int64, shape=[None, None, None],  # shape = (batch size, max number of candidate spans, max number of cand entitites)
        self.cand_entities_scores: tf.float32, shape=[None, None, None],
        self.cand_entities_labels: tf.int64, shape=[None, None, None],
        # shape = (batch_size, max number of candidate spans)
        self.cand_entities_len: tf.int64, shape=[None, None],
        self.ground_truth: tf.int64, shape=[None, None],  # shape = (batch_size, max number of candidate spans)
        self.ground_truth_len: tf.int64, shape=[None],    # shape = (batch_size)
        self.begin_gm: tf.int64, shape=[None, None],  # shape = (batch_size, max number of gold mentions)
        self.end_gm = tf.placeholder(tf.int64, shape=[None, None],
        """

        # word_char_maps.pickle存的为：vocabulary中未经编码的词汇-编号和字符-编号字典word2id, id2word,
        # char2id, id2char 以及频率阈值信息
        with open(config.base_folder + "data/tfrecords/" + self.args.experiment_name +
                  "/word_char_maps.pickle", 'rb') as handle:
            _, id2word, _, id2char, _, _ = pickle.load(handle)
            self.nwords = len(id2word)  # 词库中单词数量
            self.nchars = len(id2char)  # 词库中字符数量

        # 生成一个向量，并填补一下长度到self.cand_entities_scores（某个sample的实际候选实体数量）
        self.loss_mask = self._sequence_mask_v13(self.cand_entities_len, tf.shape(self.cand_entities_scores)[2])

    def add_placeholders(self):
        """Define placeholders = entries to computational graph"""
        self.dropout = tf.placeholder(dtype=tf.float32, shape=[], name="dropout")
        self.lr = tf.placeholder(dtype=tf.float32, shape=[], name="lr")

    def init_embeddings(self):
        print("\n!!!! init embeddings* !!!!\n")
        # read the numpy file
        # embeddings_array.npy存取的是单词字典中过滤后的每一个单词的word2vec编码,(词库单词数量×300)
        embeddings_nparray = np.load(config.base_folder + "data/tfrecords/" + self.args.experiment_name +
                                     "/embeddings_array.npy")
        # word embedding初始化运行
        self.sess.run(self.word_embedding_init, feed_dict={self.word_embeddings_placeholder: embeddings_nparray})

        # entity embedding初始化运行
        entity_embeddings_nparray = util.load_ent_vecs(self.args)
        self.sess.run(self.entity_embedding_init,
                      feed_dict={self.entity_embeddings_placeholder: entity_embeddings_nparray})

    def add_embeddings_op(self):

        print("\n!!!! add embeddings operation* !!!!\n")
        """Defines self.word_embeddings"""
        with tf.variable_scope("words"):
            _word_embeddings = tf.Variable(
                tf.constant(0.0, shape=[self.nwords, 300]),
                name="_word_embeddings",  # 变量名
                dtype=tf.float32,  # 数据类型
                trainable=False)

            # 将每个单词embedding为300维的向量，故总的形状为：词库中单词数量×300
            self.word_embeddings_placeholder = tf.placeholder(tf.float32, [self.nwords, 300])
            self.word_embedding_init = _word_embeddings.assign(self.word_embeddings_placeholder)

            # 一般做自然语言相关的。需要把每个词都映射成向量，这个向量可以是word2vec预训练好的，也可以是在网络里训练的，
            # 在网络里需要先把词的id转换成对应的向量，这个函数就是做这件事的
            # 故这里word_embeddings维度也为300维
            # b = tf.nn.embedding_lookup(c, [1, 3]) ：查找数组c中的序号为1和3的
            # self.words存储的是单词的ID
            # 下面语句作用：从编码后的单词字典中获取样本中的单词的编码，(batch, 样本单词数量, 300)
            word_embeddings = tf.nn.embedding_lookup(_word_embeddings, self.words, name="word_embeddings")
            self.pure_word_embeddings = word_embeddings
            # print("word_embeddings (after lookup) ", word_embeddings)

        with tf.variable_scope("chars"):
            if self.args.use_chars:
                # get char embeddings matrix
                _char_embeddings = tf.get_variable(
                    name="_char_embeddings",
                    dtype=tf.float32,
                    shape=[self.nchars, self.args.dim_char], trainable=True)  # self.nchars为字符字典char2id里的字符数量
                # 因self.chars: (batch, 最长的句子长度, 最长的单词的字符数)
                # 故char_embeddings：(batch, 最长的句子长度, 最长的单词的字符数, 字符编码维度)
                char_embeddings = tf.nn.embedding_lookup(_char_embeddings,
                                                         self.chars, name="char_embeddings")

                # char_embeddings: tf.float32, shape=[None, None, None, dim_char],
                # shape = (batch size, max length of sentence, max length of word, dim_char)
                # put the time dimension on axis=1
                s = tf.shape(char_embeddings)
                char_embeddings = tf.reshape(char_embeddings, shape=[s[0] * s[1], s[-2], self.args.dim_char])
                # (batch * 最长的句子长度, 最长的单词的字符数, 字符编码维度)

                char_lengths = tf.reshape(self.chars_len, shape=[s[0] * s[1]])  # chars_len存该batch全部的单词数量
                # shape = (batch_size*max_length of sentence)

                # bi lstm on chars
                # 先定义两个LSTM层（hidden_size_char默认100）
                cell_fw = tf.contrib.rnn.LSTMCell(self.args.hidden_size_char, state_is_tuple=True)
                cell_bw = tf.contrib.rnn.LSTMCell(self.args.hidden_size_char, state_is_tuple=True)
                # 让一个LSTM层用于前向、一个后向，并组合两个的结果
                # RNN的输入：一般的shape为[batch_size,seq_len,embedding_size]
                _output = tf.nn.bidirectional_dynamic_rnn(
                    cell_fw, cell_bw, char_embeddings,
                    sequence_length=char_lengths, dtype=tf.float32)

                # read and concat output
                _, ((_, output_fw), (_, output_bw)) = _output
                output = tf.concat([output_fw, output_bw], axis=-1)  # 这里将前向和后向拼接，没相加

                # shape = (batch size, max sentence length, char hidden size)
                output = tf.reshape(output, shape=[s[0], s[1], 2 * self.args.hidden_size_char])
                # print("output after char lstm ", output)

                # 原来的单词嵌入是300维，再加上单词字符LSTM编码的2×100，最后为500维
                word_embeddings = tf.concat([word_embeddings, output], axis=-1)  # concatenate word and char embeddings
                # print("word_embeddings with char after concatenation ", word_embeddings)
                # (batch, words, 300+2*100)
        self.word_embeddings = tf.nn.dropout(word_embeddings, self.dropout)

        with tf.variable_scope("entities"):
            # from preprocessing.util import load_wikiid2nnid
            import sys
            sys.path.append("..")
            from preprocessing.util import load_wikiid2nnid
            self.nentities = len(load_wikiid2nnid(extension_name=self.args.entity_extension))
            _entity_embeddings = tf.Variable(
                tf.constant(0.0, shape=[self.nentities, 300]),
                name="_entity_embeddings",
                dtype=tf.float32,
                trainable=self.args.train_ent_vecs)

            self.entity_embeddings_placeholder = tf.placeholder(tf.float32, [self.nentities, 300])
            self.entity_embedding_init = _entity_embeddings.assign(self.entity_embeddings_placeholder)

            self.entity_embeddings = tf.nn.embedding_lookup(_entity_embeddings, self.cand_entities,
                                                            name="entity_embeddings")
            self.pure_entity_embeddings = self.entity_embeddings
            if self.args.ent_vecs_regularization.startswith("l2"):  # 'l2' or 'l2dropout'
                self.entity_embeddings = tf.nn.l2_normalize(self.entity_embeddings, dim=3)
                # not necessary since i do normalization in the entity embed creation as well, just for safety
            if self.args.ent_vecs_regularization == "dropout" or \
                    self.args.ent_vecs_regularization == "l2dropout":
                self.entity_embeddings = tf.nn.dropout(self.entity_embeddings, self.dropout)
            # print("entity_embeddings = ", self.entity_embeddings)

        with tf.variable_scope("first_paragraph"):
            # 获得候选实体摘要的第一段落的embeddings

            # _word_embeddings = tf.get_variable(
            #     name="_first_paragraph_embeddings",
            #     dtype=tf.float32,
            #     shape=[self.nwords, 300], trainable=True)
            first_paragraph_embeddings = tf.nn.embedding_lookup(_word_embeddings, self.cand_first_paragraph, name="first_paragraph_embeddings")
            s = tf.shape(first_paragraph_embeddings)


    def add_context_emb_op(self):
        print("\n!!!! add context embeddings operation* !!!!\n")
        """this method creates the bidirectional LSTM layer (takes input the v_k vectors and outputs the
        context-aware word embeddings x_k)"""
        with tf.variable_scope("context-bi-lstm"):
            cell_fw = tf.contrib.rnn.LSTMCell(self.args.hidden_size_lstm)  # hidden_size_lstm 默认=300
            cell_bw = tf.contrib.rnn.LSTMCell(self.args.hidden_size_lstm)
            (output_fw, output_bw), _ = tf.nn.bidirectional_dynamic_rnn(
                cell_fw, cell_bw, self.word_embeddings,
                sequence_length=self.words_len, dtype=tf.float32)
            output = tf.concat([output_fw, output_bw], axis=-1)
            self.context_emb = tf.nn.dropout(output, self.dropout)
            # print("context_emb = ", self.context_emb)  # [batch, words, 300]

    def add_span_emb_op(self):
        mention_emb_list = []
        # span embedding based on boundaries (start, end) and head mechanism. but do that on top of contextual bilistm
        # output or on top of original word+char embeddings. this flag determines that. The parer reports results when
        # using the contextual lstm emb as it achieves better score. Used for ablation studies.
        # 这里默认boundaries_input_vecs等于x_k(即上一步的self.context_emb)
        boundaries_input_vecs = self.word_embeddings if self.args.span_boundaries_from_wordemb else self.context_emb

        # the span embedding is modeled by g^m = [x_q; x_r; \hat(x)^m]  (formula (2) of paper)
        # "boundaries" mean use x_q and x_r.   "head" means use also the head mechanism \hat(x)^m (formula (3))
        # 找各span mention开始的位置（这话错了），应该是use x_q and x_r
        if self.args.span_emb.find("boundaries") != -1:
            # shape (batch, num_of_cand_spans, emb)
            # tf的gather_nd(params, indices, name=None)主要功能是根据indices描述的索引，提取params上的元素， 重新构建一个tensor
            # tf.stack()是一个矩阵拼接函数
            # tf.tile(input, multiples, name=None)是tensorflow中对张量进行复制的函数. multiples:同一维度上复制的次数
            mention_start_emb = tf.gather_nd(boundaries_input_vecs, tf.stack(
                [tf.tile(tf.expand_dims(tf.range(tf.shape(self.begin_span)[0]), 1), [1, tf.shape(self.begin_span)[1]]),
                 self.begin_span], 2))  # extracts the x_q embedding for each candidate span
            # the tile command creates a 2d tensor with the batch information. first lines contains only zeros, second
            # line ones etc...  because the begin_span tensor has the information which word inside this sentence is the
            # beginning of the candidate span.
            mention_emb_list.append(mention_start_emb)  # 实体提及开始的单词集合追加到gm

            mention_end_emb = tf.gather_nd(boundaries_input_vecs, tf.stack(
                [tf.tile(tf.expand_dims(tf.range(tf.shape(self.begin_span)[0]), 1), [1, tf.shape(self.begin_span)[1]]),
                 tf.nn.relu(self.end_span - 1)], 2))  # -1 because the end of span in exclusive  [start, end)
            # relu so that the 0 doesn't become -1 of course no valid candidate span end index is zero since [0,0) is empty
            mention_emb_list.append(mention_end_emb)  # 实体提及结束的单词集合追加到gm
            # print("\nmention_start_emb = ", mention_start_emb)
            # print("\n****mention_end_emb = ", mention_end_emb)

        mention_width = self.end_span - self.begin_span  # [batch, num_mentions]     the width of each candidate span

        """
        取消软头部，因为其效果不好
        # 找各span mention结束的位置（这话错了），应该是use软头部
        if self.args.span_emb.find("head") != -1:  # here the attention is computed
            # here the \hat(x)^m is computed (formula (2) and (3))
            self.max_mention_width = tf.minimum(self.args.max_mention_width,
                                                tf.reduce_max(self.end_span - self.begin_span))
            mention_indices = tf.range(self.max_mention_width) + \
                              tf.expand_dims(self.begin_span, 2)  # [batch, num_mentions, max_mention_width]
            mention_indices = tf.minimum(tf.shape(self.word_embeddings)[1] - 1,
                                         mention_indices)  # [batch, num_mentions, max_mention_width]
            # print("mention_indices = ", mention_indices)
            batch_index = tf.tile(tf.expand_dims(tf.expand_dims(tf.range(tf.shape(mention_indices)[0]), 1), 2),
                                  [1, tf.shape(mention_indices)[1], tf.shape(mention_indices)[2]])
            mention_indices = tf.stack([batch_index, mention_indices], 3)
            # [batch, num_mentions, max_mention_width, [row,col] ]    4d tensor

            # for the boundaries we had the option to take them either from x_k (output of bilstm) or from v_k
            # the head is derived either from the same option as boundaries or from the v_k.
            head_input_vecs = boundaries_input_vecs if self.args.model_heads_from_bilstm else self.word_embeddings
            mention_text_emb = tf.gather_nd(head_input_vecs, mention_indices)
            # [batch, num_mentions, max_mention_width, 500 ]    4d tensor
            # print("mention_text_emb = ", mention_text_emb)

            # 计算x^m， embedding后的soft head
            with tf.variable_scope("head_scores"):
                # from [batch, max_sent_len, 300] to [batch, max_sent_len, 1]
                self.head_scores = util.projection(boundaries_input_vecs, 1)
            # [batch, num_mentions, max_mention_width, 1]
            mention_head_scores = tf.gather_nd(self.head_scores, mention_indices)
            # print("mention_head_scores = ", mention_head_scores)

            # depending on tensorflow version we do the same with different operations (since each candidate span is not
            # of the same length we mask out the invalid indices created above (mention_indices)).
            temp_mask = self._sequence_mask_v13(mention_width, self.max_mention_width)
            # still code for masking invalid indices for the head computation
            mention_mask = tf.expand_dims(temp_mask, 3)  # [batch, num_mentions, max_mention_width, 1]
            mention_mask = tf.minimum(1.0, tf.maximum(self.args.zero, mention_mask))  # 1e-3
            # formula (3) computation
            mention_attention = tf.nn.softmax(mention_head_scores + tf.log(mention_mask),
                                              dim=2)  # [batch, num_mentions, max_mention_width, 1]
            mention_head_emb = tf.reduce_sum(mention_attention * mention_text_emb, 2)  # [batch, num_mentions, emb]
            # print("mention_head_emb = ", mention_head_emb)
            mention_emb_list.append(mention_head_emb)  # 实体提及的soft head单词集合追加到gm
        """

        self.span_emb = tf.concat(mention_emb_list, 2)  # [batch, num_mentions, emb i.e. 1700] formula (2) concatenation
        # print("span_emb = ", self.span_emb)

    def add_lstm_score_op(self):
        with tf.variable_scope("span_emb_ffnn"):
            # [batch, num_mentions, 300]
            # the span embedding can have different size depending on the chosen hyperparameters. We project it to 300
            # dims to match the entity embeddings  (formula 4)
            if self.args.span_emb_ffnn[0] == 0:  # 不执行式(4)，不使用FFNN映射gm，但是维度还是要整理统一一下
                span_emb_projected = util.projection(self.span_emb, 300)  # self.span_emb：上一步骤产生的span的embedding
            else:  # 执行式(4)，使用FFNN映射gm
                hidden_layers, hidden_size = self.args.span_emb_ffnn[0], self.args.span_emb_ffnn[1]
                span_emb_projected = util.ffnn(self.span_emb, hidden_layers, hidden_size, 300,
                                               self.dropout if self.args.ffnn_dropout else None)
                # print("span_emb_projected = ", span_emb_projected)
        # formula (6) <x^m, y_j>   computation. this is the lstm score
        # 计算实体提及和候选实体的得分，公式(6)的<x^m, y_j>部分：m-ej lstm similarity scores <x^m, y_j>
        # tf.matmul(a,b)：矩阵a、b相乘
        scores = tf.matmul(tf.expand_dims(span_emb_projected, 2), self.entity_embeddings, transpose_b=True)
        # print("scores = ", scores)
        self.similarity_scores = tf.squeeze(scores, axis=2)  # [batch, num_mentions, 1, 30] 30因每个提及30个候选实体
        # print("scores = ", self.similarity_scores)   # [batch, num_mentions, 30]

    def add_local_attention_op(self):
        attention_entity_emb = self.pure_entity_embeddings if self.args.attention_ent_vecs_no_regularization else self.entity_embeddings
        with tf.variable_scope("attention"):
            K = self.args.attention_K
            left_mask = self._sequence_mask_v13(self.begin_span, K)  # number of words on the left (left window)
            right_mask = self._sequence_mask_v13(tf.expand_dims(self.words_len, 1) - self.end_span, K)
            # number of words on the right. of course i don't get more than K even if more words exist.
            ctxt_mask = tf.concat([left_mask, right_mask], 2)  # [batch, num_of_spans, 2*K]
            ctxt_mask = tf.log(tf.minimum(1.0, tf.maximum(self.args.zero, ctxt_mask)))
            #  T,   T,  T, F,  F | T,  T,  F,  F,  F
            # -1, -2, -3, -4, -5  +0, +1, +2, +3, +4

            leftctxt_indices = tf.maximum(0, tf.range(-1, -K - 1, -1) +
                                          tf.expand_dims(self.begin_span, 2))  # [batch, num_mentions, K]
            rightctxt_indices = tf.minimum(tf.shape(self.pure_word_embeddings)[1] - 1, tf.range(K) +
                                           tf.expand_dims(self.end_span, 2))  # [batch, num_mentions, K]
            ctxt_indices = tf.concat([leftctxt_indices, rightctxt_indices], 2)  # [batch, num_mentions, 2*K]

            batch_index = tf.tile(tf.expand_dims(tf.expand_dims(tf.range(tf.shape(ctxt_indices)[0]), 1), 2),
                                  [1, tf.shape(ctxt_indices)[1], tf.shape(ctxt_indices)[2]])
            ctxt_indices = tf.stack([batch_index, ctxt_indices], 3)
            # [batch, num_of_spans, 2*K, 2]   the last dimension is row,col for gather_nd
            # [batch, num_of_spans, 2*K, [row,col]]

            att_x_w = self.pure_word_embeddings  # [batch, max_sent_len, 300]
            if self.args.attention_on_lstm and self.args.nn_components.find("lstm") != -1:
                # ablation: here the attention is computed on the output of the lstm layer x_k instead of using the
                # pure word2vec vectors. (word2vec used in paper).
                att_x_w = util.projection(self.context_emb,
                                          300)  # if tf.shape(self.context_emb)[-1] != 300 else self.context_emb

            ctxt_word_emb = tf.gather_nd(att_x_w, ctxt_indices)
            # [batch, num_of_spans, 2K, emb_size]    emb_size = 300  only pure word emb used  (word2vec)
            #  and not after we add char emb and dropout

            # in this implementation we don't use the diagonal A and B arrays that are mentioned in
            # Ganea and Hoffmann 2017 (only used in the ablations)
            temp = attention_entity_emb
            if self.args.attention_use_AB:
                att_A = tf.get_variable("att_A", [300])
                temp = att_A * attention_entity_emb
            scores = tf.matmul(ctxt_word_emb, temp, transpose_b=True)
            scores = tf.reduce_max(scores, reduction_indices=[
                -1])  # max score of each word for each span acquired from any cand entity
            scores = scores + ctxt_mask  # some words are not valid out of window so we assign to them very low score
            top_values, _ = tf.nn.top_k(scores, self.args.attention_R)
            # [batch, num_of_spans, R]
            R_value = top_values[:, :, -1]  # [batch, num_of_spans]
            R_value = tf.maximum(self.args.zero, R_value)  # so to avoid keeping words that
            # have max score with any of the entities <=0 (also score = 0 can have words with
            # padding candidate entities)

            threshold = tf.tile(tf.expand_dims(R_value, 2), [1, 1, 2 * K])
            # [batch, num_of_spans, 2K]
            scores = scores - tf.to_float(((scores - threshold) < 0)) * 50  # 50 where score<thr, 0 where score>=thr
            scores = tf.nn.softmax(scores, dim=2)  # [batch, num_of_spans, 2K]
            scores = tf.expand_dims(scores, 3)  # [batch, num_of_spans, 2K, 1]
            #    [batch, num_of_spans, 2K, 1]  *  [batch, num_of_spans, 2K, emb_size]
            # =  [batch, num_of_spans, 2K, emb_size]
            x_c = tf.reduce_sum(scores * ctxt_word_emb, 2)  # =  [batch, num_of_spans, emb_size]
            if self.args.attention_use_AB:
                att_B = tf.get_variable("att_B", [300])
                x_c = att_B * x_c
            x_c = tf.expand_dims(x_c, 3)  # [batch, num_of_spans, emb_size, 1]
            # [batch, num_of_spans, 30, emb_size=300]  mul with  [batch, num_of_spans, emb_size, 1]
            x_e__x_c = tf.matmul(attention_entity_emb, x_c)  # [batch, num_of_spans, 30, 1]
            x_e__x_c = tf.squeeze(x_e__x_c, axis=3)  # [batch, num_of_spans, 30]
            self.attention_scores = x_e__x_c

    def add_cand_ent_scores_op(self):

        # log p(ej|m)
        self.log_cand_entities_scores = tf.log(tf.minimum(1.0, tf.maximum(self.args.zero, self.cand_entities_scores)))

        # 要送入FFNN2的三个部分
        stack_values = []
        if self.args.nn_components.find("lstm") != -1:
            stack_values.append(self.similarity_scores)
        if self.args.nn_components.find("pem") != -1:
            stack_values.append(self.log_cand_entities_scores)
        if self.args.nn_components.find("attention") != -1:
            stack_values.append(self.attention_scores)

        scalar_predictors = tf.stack(stack_values, 3)
        # print("scalar_predictors = ", scalar_predictors)   # [batch, num_mentions, 30, 3]

        with tf.variable_scope("similarity_and_prior_ffnn"):
            if self.args.final_score_ffnn[0] == 0:  # 不使用FFNN2,则整理一下输出
                self.final_scores = util.projection(scalar_predictors, 1)  # [batch, num_mentions, 30, 1]
            else:  # 使用FFNN2
                hidden_layers, hidden_size = self.args.final_score_ffnn[0], self.args.final_score_ffnn[1]
                self.final_scores = util.ffnn(scalar_predictors, hidden_layers, hidden_size, 1,
                                              self.dropout if self.args.ffnn_dropout else None)
            self.final_scores = tf.squeeze(self.final_scores, axis=3)  # squeeze to [batch, num_mentions, 30]
            # print("final_scores = ", self.final_scores)

    def add_global_voting_op(self):
        with tf.variable_scope("global_voting"):

            # 全局投票前的得分
            self.final_scores_before_global = - (1 - self.loss_mask) * 50 + self.final_scores

            # 计算可参与投票的实体
            # 计算可参与投票的实体(gmask是一堆True和False组成的矩阵)
            gmask = tf.to_float(((self.final_scores_before_global - self.args.global_thr) >= 0))  # [b,s,30]
            # 获得可参与投票的实体的embedding
            masked_entity_emb = self.pure_entity_embeddings * tf.expand_dims(gmask, axis=3)  # [b,s,30,300] * [b,s,30,1]

            batch_size = tf.shape(masked_entity_emb)[0]

            # tf.reduce_sum()作用是按一定方式计算张量中元素之和,故这里是计算yGm
            all_voters_emb = tf.reduce_sum(tf.reshape(masked_entity_emb, [batch_size, -1, 300]), axis=1,
                                           keep_dims=True)  # [b, 1, 300]
            # 为什么还要下面这两行？？？
            span_voters_emb = tf.reduce_sum(masked_entity_emb, axis=2)  # [batch, num_of_spans, 300]
            valid_voters_emb = all_voters_emb - span_voters_emb
            # [b, 1, 300] - [batch, spans, 300] = [batch, spans, 300]  (broadcasting)
            # [300] - [batch, spans, 300]  = [batch, spans, 300]  (broadcasting)
            valid_voters_emb = tf.nn.l2_normalize(valid_voters_emb, dim=2)

            self.global_voting_scores = tf.squeeze(
                tf.matmul(self.pure_entity_embeddings, tf.expand_dims(valid_voters_emb, axis=3)), axis=3)
            # [b,s,30,300] matmul [b,s,300,1] --> [b,s,30,1]-->[b,s,30]

            scalar_predictors = tf.stack([self.final_scores_before_global, self.global_voting_scores], 3)
            # print("scalar_predictors = ", scalar_predictors)   #[b, s, 30, 2]
            with tf.variable_scope("psi_and_global_ffnn"):
                if self.args.global_score_ffnn[0] == 0:  # 不适用FFNN3,整理一下输出
                    self.final_scores = util.projection(scalar_predictors, 1)
                else:  # 使用FFNN3
                    hidden_layers, hidden_size = self.args.global_score_ffnn[0], self.args.global_score_ffnn[1]
                    self.final_scores = util.ffnn(scalar_predictors, hidden_layers, hidden_size, 1,
                                                  self.dropout if self.args.ffnn_dropout else None)
                # [batch, num_mentions, 30, 1] squeeze to [batch, num_mentions, 30]
                self.final_scores = tf.squeeze(self.final_scores, axis=3)
                # print("final_scores = ", self.final_scores)

    def add_loss_op(self):
        cand_entities_labels = tf.cast(self.cand_entities_labels, tf.float32)
        # 定义两个loss
        loss1 = cand_entities_labels * tf.nn.relu(self.args.gamma_thr - self.final_scores)
        loss2 = (1 - cand_entities_labels) * tf.nn.relu(self.final_scores)
        self.loss = loss1 + loss2
        if self.args.nn_components.find("global") != -1 and not self.args.global_one_loss:
            loss3 = cand_entities_labels * tf.nn.relu(self.args.gamma_thr - self.final_scores_before_global)
            loss4 = (1 - cand_entities_labels) * tf.nn.relu(self.final_scores_before_global)
            self.loss = loss1 + loss2 + loss3 + loss4
        # print("loss_mask = ", loss_mask)
        self.loss = self.loss_mask * self.loss
        self.loss = tf.reduce_sum(self.loss)
        # for tensorboard
        # tf.summary.scalar("loss", self.loss)

    def build(self):

        # dropout、lr占位
        self.add_placeholders()

        # 论文里Word and char Embeddings，对词库的每个单词单独操作，产生v_k
        self.add_embeddings_op()

        # 论文里Mention Represention
        if self.args.nn_components.find("lstm") != -1:
            # ①对v_k使用BiLSTM，产生x_k
            self.add_context_emb_op()
            # ② 为每个可能的提及产生最终的向量（式(2)）
            self.add_span_emb_op()
            # 首先判断是否执行式(4)FFNN1；然后论文Final Local Score：计算实体提及和候选实体的
            # 得分（公式(6)的<xm，yj>部分）：m-ej lstm similarity scores <x^m, y_j>
            self.add_lstm_score_op()
        # 论文Long Range Contex Attention
        if self.args.nn_components.find("attention") != -1:
            self.add_local_attention_op()
        # 论文Entity Embeddings：计算log p(ej|m) （这部分也是要送入到FFNN2的）
        # 然后结合log p(ej|m)、m-ej lstm similarity、long rang attention,输入到FFNN2
        self.add_cand_ent_scores_op()
        # 论文Global Disambiguation
        if self.args.nn_components.find("global") != -1:
            self.add_global_voting_op()

        if self.args.running_mode.startswith("train"):
            # 定义损失函数
            self.add_loss_op()
            # Generic functions that add training op
            # 定义Optimizer和定义训练
            self.add_train_op(self.args.lr_method, self.lr, self.loss, self.args.clip)
            # 将之前定义的所有summary整合在一起，在一个程序中定义的写日志操作比较多，如果一一调用，将会十分麻烦，
            # 所以Tensorflow提供了tf.summary.merge_all()函数将所有summary整理在一起。在TensorFlow程序执行的时候，
            # 只需要运行这一个操作就可以将代码中定义的所有【写日志操作】执行一次，从而将所有的日志写入【日志文件】。
            self.merged_summary_op = tf.summary.merge_all()

        if self.args.running_mode == "train_continue":
            self.restore_session("latest")
        elif self.args.running_mode == "train":
            self.initialize_session()  # now self.sess is defined and vars are init
            self.init_embeddings()

        # if we run the evaluate.py script then we should call explicitly the model.restore("ed")
        # or model.restore("el"). here it doesn't initialize or restore values for the evaluate.py
        # case.

    def _sequence_mask_v13(self, mytensor, max_width):
        """mytensor is a 2d tensor"""
        if not tf.__version__.startswith("1.4"):
            temp_shape = tf.shape(mytensor)
            temp = tf.sequence_mask(tf.reshape(mytensor, [-1]), max_width, dtype=tf.float32)
            temp_mask = tf.reshape(temp, [temp_shape[0], temp_shape[1], tf.shape(temp)[-1]])
        else:
            temp_mask = tf.sequence_mask(mytensor, max_width, dtype=tf.float32)
        return temp_mask
