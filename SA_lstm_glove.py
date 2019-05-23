import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.utils.data as Data


def vocab_list(train_data, validation_data, test_data):
    word_list = []
    train_words = []
    validation_words = []
    test_words = []

    for phrase in train_data:
        t = []
        for word in phrase.split(' '):
            word_list.append(word.lower())
            t.append(word.lower())
        train_words.append(t)

    for phrase in validation_data:
        t = []
        for word in phrase.split(' '):
            word_list.append(word.lower())
            t.append(word.lower())
        validation_words.append(t)

    for phrase in test_data:
        t = []
        for word in phrase.split(' '):
            t.append(word.lower())
        test_words.append(t)
    return list(set(word_list)), train_words, validation_words, test_words


def encode_phrase(data, word2idx):
    encode_data = []
    for phrase in data:
        t = []
        for word in phrase:
            if word in word2idx:
                t.append(word2idx[word])
            else:
                t.append(0)
        encode_data.append(t)
    return encode_data


def pad_phrase(encode_data, max_length):
    pad_encode_data = []
    for phrase in encode_data:
        temp_phrase = phrase
        if len(temp_phrase) > max_length:
            pad_encode_data.append(temp_phrase[:max_length])
        else:
            while len(temp_phrase) < max_length:
                temp_phrase.append(0)
            pad_encode_data.append(temp_phrase)
    return pad_encode_data


def get_glove(words_set):
    glove = torch.zeros([len(words_set) + 1, 50])
    word2idx = {}
    word2idx['<unk>'] = 0
    idx = 1
    with open("./glove/glove.6B.50d.txt") as glove_file:
        for line in glove_file:
            temp = line.split()
            if temp[0] in words_set:
                glove[idx] = torch.from_numpy(np.array(temp[1:]).astype(np.float))
                word2idx[temp[0]] = idx
                idx = idx + 1
    return word2idx, glove[:idx, :]


def precess_dataset(max_length):
    train_dataset = pd.read_csv("./dataset/train.tsv", sep='\t')
    test_dataset = pd.read_csv("./dataset/test.tsv", sep='\t')
    # print(train_dataset.info())

    train_phrase = train_dataset['Phrase']
    test_phrase = test_dataset['Phrase']
    train_y = train_dataset['Sentiment'].values

    validation_phrase = train_phrase[120000:]
    train_phrase = train_phrase[:120000]
    validation_y = train_y[120000:]
    train_y = train_y[:120000]

    word_list, train_words, validation_words, test_words = vocab_list(train_phrase, validation_phrase, test_phrase)
    word_size = len(word_list) + 1
    word2idx, glove = get_glove(set(word_list))

    train_x = pad_phrase(encode_phrase(train_words, word2idx), max_length)
    validation_x = pad_phrase(encode_phrase(validation_words, word2idx), max_length)
    test_x = pad_phrase(encode_phrase(test_words, word2idx), max_length)

    return len(word2idx), word2idx, glove, train_x, validation_x, train_y, validation_y, test_x


class MySA(nn.Module):
    def __init__(self, vocb_size, emd_dim, hidden_size, num_layers, class_size, glove):
        super(MySA, self).__init__()

        # self.embedding = nn.Embedding(vocb_size, emd_dim)
        self.embedding = nn.Embedding.from_pretrained(glove, freeze=False)
        self.lstm = nn.LSTM(input_size=emd_dim,
                            hidden_size=hidden_size,
                            num_layers=num_layers,
                            bidirectional=True)
        self.liner = nn.Linear(hidden_size * 4, 32)
        self.dropout = nn.Dropout(0.5)
        self.predict = nn.Linear(32, class_size)

    def forward(self, inputs):
        embed = self.embedding(inputs)
        status, hidden = self.lstm(embed.permute(1, 0, 2))
        encode = torch.cat((status[0], status[-1]), dim=1)
        out = self.liner(encode)
        out = self.dropout(out)
        out = self.predict(out)
        return out


LR = 0.01
EPOCH = 3
MAX_LENGTH = 16
BATCH_SIZE = 128

vocb_size, word2idx, glove, train_x, validation_x, train_y, validation_y, test_x = precess_dataset(MAX_LENGTH)
train_x = torch.LongTensor(train_x)
train_y = torch.tensor(train_y)
validation_x = torch.LongTensor(validation_x)
validation_y = torch.tensor(validation_y)
test_x = torch.LongTensor(test_x)

train_set = Data.TensorDataset(train_x, train_y)
train_loader = Data.DataLoader(dataset=train_set,
                               batch_size=BATCH_SIZE,
                               shuffle=True)

mySA = MySA(vocb_size=vocb_size,
            emd_dim=50,
            hidden_size=50,
            num_layers=1,
            class_size=5,
            glove=glove)
optimizer = torch.optim.Adam(mySA.parameters(), lr=LR)
loss_func = nn.CrossEntropyLoss()
print(glove.size())
print(mySA.embedding.weight.size())
mySA.cuda()
loss_func.cuda()

for epoch in range(EPOCH):
    for idx, (x, y) in enumerate(train_loader):
        x = x.cuda()
        y = y.cuda()

        pred_train = mySA(x)
        loss = loss_func(pred_train, y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if idx % 100 == 0:
            mySA.eval()
            validation_x = validation_x.cuda()
            validation_y = validation_y.cuda()

            pred_validation = mySA(validation_x)
            pred_output = torch.max(pred_validation, dim=1)[1]
            accuracy = float(torch.sum(pred_output == validation_y)) / float(validation_y.size(0))
            print('Epoch: ', epoch, '| train loss: %.4f' % loss.item(), '| validation accuracy: %.4f' % accuracy)
            mySA.train()

mySA.eval()
test_x = test_x.cuda()
pred_test = mySA(test_x)

pred_output = torch.max(pred_test, dim=1)[1]
pred_output = pred_output.type(torch.int32)

submit_file = pd.read_csv("./dataset/test.tsv", sep='\t')
del submit_file['SentenceId']
del submit_file['Phrase']

submit_file['Sentiment'] = pred_output.cpu()
submit_file.to_csv("./dataset/submission.csv", index=False)
print(submit_file.info())