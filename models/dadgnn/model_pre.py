from random import randint
import random
import dgl
import torch
import torch.nn.functional as F
import numpy as np
import gensim
from models.dadgnn.attention_diffusion import GATNet
from dgl.nn.pytorch.glob import WeightAndSum


class DADGNN(torch.nn.Module):
    def __init__(self,
                 num_hidden,
                 num_layers,
                 num_heads,
                 k,
                 alpha,
                 vocab,
                 n_gram,
                 drop_out,
                 class_num,
                 num_feats,
                 max_length=350,
                 cuda=True,
                 ):
        super(DADGNN, self).__init__()

        self.is_cuda = cuda
        self.vocab = vocab

        # self.node_hidden = torch.nn.Embedding(len(vocab), num_feats)
        # self.node_hidden.weight.data.copy_(torch.tensor(self.load_word2vec('/home/zhuozj/Workspace/02_Deep_Learning/01.Datasets/glove.6B.300d.txt')))
        # self.node_hidden.weight.requires_grad = True

        self.len_vocab = len(vocab)
        self.ngram = n_gram
        self.max_length = max_length

        self.gatnet = GATNet(class_num, class_num, class_num, num_layers, k, alpha, num_heads, merge='mean')
        self.dropout = torch.nn.Dropout(p=drop_out)
        self.activation = torch.nn.ReLU()

        self.linear1 = torch.nn.Linear(num_feats, num_hidden, bias=True)
        self.bn1 = torch.nn.BatchNorm1d(num_hidden)
        self.linear2 = torch.nn.Linear(num_hidden, class_num, bias=True)
        self.bn2 = torch.nn.BatchNorm1d(class_num)
        self.weight_and_sum = WeightAndSum(class_num)


    def reset(self):
      gain = torch.nn.init.calculate_gain("relu")
      torch.nn.init.xavier_normal_(self.Linear.weight, gain=gain)
      torch.nn.init.xavier_normal_(self.gate_nn.weight, gain=gain)
      torch.nn.init.xavier_normal_(self.attn_fc.weight, gain=gain)

    def load_word2vec(self, word2vec_file):
        model = gensim.models.KeyedVectors.load_word2vec_format(word2vec_file)

        embedding_matrix = []

        for word in self.vocab:
            try:
                embedding_matrix.append(model[word])
            except KeyError:
                embedding_matrix.append(np.random.uniform(-0.1,0.1,300))

        embedding_matrix = np.array(embedding_matrix)

        return embedding_matrix

    def add_seq_edges(self, doc_ids: list, old_to_new: dict):

        edges = []
        old_edge_id = []

        for index, src_word_old in enumerate(doc_ids):
            src = old_to_new[src_word_old]
            for i in range(max(0, index - self.ngram), min(index + self.ngram + 1, len(doc_ids))):
                dst_word_old = doc_ids[i]
                dst = old_to_new[dst_word_old]
                edges.append([src, dst])

        return edges

    def seq_to_graph(self, feature: torch.tensor) -> dgl.DGLGraph():

        # if len(doc_ids) > self.max_length:
            # doc_ids = doc_ids[:self.max_length]
        doc_ids = list(range(0, feature.shape[0]))  # 用来生成图的边，id用来对位置做个标记
        random.shuffle(doc_ids)

        local_vocab = set(doc_ids)

        old_to_new = dict(zip(local_vocab, range(len(local_vocab))))

        if self.is_cuda:
            local_vocab = torch.tensor(list(local_vocab)).cuda()
        else:
            local_vocab = torch.tensor(list(local_vocab))

        sub_graph = dgl.DGLGraph().to('cuda')
        sub_graph.add_nodes(len(local_vocab))
        # local_node_hidden = self.node_hidden(local_vocab)

        sub_graph.ndata['k'] = feature
        seq_edges = self.add_seq_edges(doc_ids, old_to_new)
        edges = []
        edges.extend(seq_edges)
        srcs, dsts = zip(*edges)
        sub_graph.add_edges(srcs, dsts)

        return sub_graph

    def forward(self, features):

        sub_graphs = [self.seq_to_graph(f) for f in features]
        batch_graph = dgl.batch(sub_graphs)
        batch_f = self.dropout(batch_graph.ndata['k'])
        # batch_f = self.activation(self.linear1(batch_f))
        # batch_f = self.linear2(self.dropout(batch_f))
        h1 = self.gatnet(batch_graph, batch_f)
        h1 = h1.reshape(features.shape)

        # h1 = self.weight_and_sum(batch_graph, h1)

        return h1
