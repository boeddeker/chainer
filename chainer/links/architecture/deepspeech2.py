import six

from chainer.functions.array import concat
from chainer.functions.array import split_axis
from chainer import link
from chainer.links.connection import convolution_2d as C
from chainer.links.connection import linear as L
from chainer.links.connection import lstm
from chainer.links.normalization import batch_normalization as B


class BRNN(link.Chain):
    def __init__(self, input_dim, output_dim):
        forward = lstm.LSTM(input_dim, output_dim)
        reverse = lstm.LSTM(input_dim, output_dim)
        super(BRNN, self).__init__(forward=forward, reverse=reverse)

    def reset_state(self):
        self.forward.reset_state()
        self.reverse.reset_state()

    def __call__(self, xs, train=True):
        N = len(xs)
        x_forward = [self.forward(x) for x in xs]
        x_reverse = [self.reverse(xs[n]) for n
                     in six.moves.range(N - 1, -1, -1)]
        return [x_f + x_r for x_f, x_r in zip(x_forward, x_reverse)]


class ConvBN(link.Chain):
    def __init__(self, *args, **kwargs):
        conv = C.Convolution2D(*args, **kwargs)
        out_channel = conv.W.data.shape[0]
        batch_norm = B.BatchNormalization(out_channel)
        super(ConvBN, self).__init__(conv=conv, batch_norm=batch_norm)

    def __call__(self, x, train=True):
        x = self.conv(x)
        return self.batch_norm(x, test=not train)


class Sequential(link.ChainList):
    def __call__(self, x, train):
        for l in self:
            x = l(x, train)
        return x


class DeepSpeech2(link.Chain):

    def __init__(self):
        c1 = ConvBN(1, 32, (41, 11), 2)
        c2 = ConvBN(32, 32, (21, 11), 2)
        c3 = ConvBN(32, 32, (21, 11), 2)
        convolution = Sequential(c1, c2, c3)
        brnn1 = BRNN(160, 400)
        brnn2 = BRNN(400, 400)
        recurrent = Sequential(brnn1, brnn2)
        linear = L.Linear(1600, 28)
        super(DeepSpeech2, self).__init__(convolution=convolution,
                                          recurrent=recurrent,
                                          linear=linear)

    def __call__(self, x, train=True):
        x = self.convolution(x, train)
        xs = split_axis.split_axis(x, x.data.shape[-1], 3)
        for x in xs:
            x.data = self.xp.ascontiguousarray(x.data)
        for r in self.recurrent:
            r.reset_state()
        xs = self.recurrent(xs, train)
        x = concat.concat(xs, 1)
        x = self.linear(x)
        return x