import argparse
import os
import random

import tensorflow as tf
from tensorflow.contrib import seq2seq
from gensim.models import KeyedVectors


parser = argparse.ArgumentParser()

# Hyperparameter args
parser.add_argument('--initial_lr', type=float, default=1e-3,
  help="Initial learning rate.")
parser.add_argument('--vocabulary_size', type=int, default=20000,
  help="Keep only the n most common words of the training data.")
parser.add_argument('--batch_size', type=int, default=16,
  help="Stochastic gradient descent minibatch size.")
parser.add_argument('--hidden_size', type=int, default=512,
  help="Number of hidden units for the encoder and decoder GRUs.")
parser.add_argument('--max_length', type=int, default=40,
  help="Truncate input and output sentences to maximum length n.")
parser.add_argument('--sample_prob', type=float, default=.3,
  help="Decoder probability to sample from its predictions duing training.")
parser.add_argument('--max_grad_norm', type=float, default=5.,
  help="Clip gradients to the specified maximum norm.")
parser.add_argument('--train_embeddings', type=bool, default=False,
  help="Set to backpropagate over the word embedding matrix.")
parser.add_argument('--eos_token', type=bool, default=False,
  help="Set to use the end-of-string token when running on inference.")
parser.add_argument('--epochs', type=int, default=10,
  help="Number of epochs to run when training the model.")

# Configuration args
parser.add_argument('--encode', type=str, default='',
  help="Set to a file path to obtain sentence vectors for the given lines.")
parser.add_argument('--embeddings_path', type=str, default="./word2vecModel",
  help="Path to the pre-trained word embeddings model.")
parser.add_argument('--dataset_path', type=str, default="./books",
  help="Path to the BookCorpus dataset files.")
parser.add_argument('--model_name', type=str, default="default",
  help="Will save/restore model in ./output/[model_name].")

FLAGS = parser.parse_args()


def get_sequence_length(seq):
  """Get the length of the provided integer sequence.
     NOTE: this method assumes the padding id is 0."""
  return tf.reduce_sum(tf.sign(seq), reduction_indices=1)


def build_encoder(inputs, seq_length):
  """When called, adds the encoder layer to the computational graph."""
  fw_cell = tf.nn.rnn_cell.GRUCell(FLAGS.hidden_size, name="encoder_fw")
  bw_cell = tf.nn.rnn_cell.GRUCell(FLAGS.hidden_size, name="encoder_bw")
  return tf.nn.bidirectional_dynamic_rnn(
    fw_cell, bw_cell, inputs, sequence_length=seq_length, dtype=tf.float32)


def build_decoder(thought, labels, embedding_matrix, name_id=0):
  """When called, adds a decoder layer to the computational graph."""
  cell = tf.nn.rnn_cell.GRUCell(FLAGS.hidden_size, name="decoder%d" % name_id)
  
  # For convenience-- this gets passed as an argument later.
  def get_embeddings(query):
    return tf.nn.embedding_lookup(embedding_matrix, query)

  # Scheduled sampling with constant probability. Labels are shifted to the
  # right by adding a start-of-string token (id: 2).
  sos_tokens = tf.tile([[2]], [FLAGS.batch_size, 1])
  shifted_labels = tf.concat([sos_tokens, labels[::-1]], axis=1)
  seq_length = get_sequence_length(shifted_labels)
  decoder_in = get_embeddings(shifted_labels)
  helper = seq2seq.ScheduledEmbeddingTrainingHelper(
    decoder_in, seq_length, get_embeddings, FLAGS.sample_prob)
  # Final layer for both decoders that converts decoder output to predictions.
  if name_id > 0:
     tf.get_variable_scope().reuse_variables()
  output_layer = tf.layers.Dense(FLAGS.vocabulary_size, name="output_layer")
  decoder = seq2seq.BasicDecoder(
    cell, helper, thought, output_layer=output_layer)
  return seq2seq.dynamic_decode(decoder, impute_finished=True)


def build_model():
  """When called, builds the whole computational graph.."""
  inputs = tf.placeholder(
    tf.int32, shape=[FLAGS.batch_size, FLAGS.max_length], name="inputs")
  fw_labels = tf.placeholder(
    tf.int32, shape=[FLAGS.batch_size, FLAGS.max_length], name="fw_labels")
  bw_labels = tf.placeholder(
    tf.int32, shape=[FLAGS.batch_size, FLAGS.max_length], name="bw_labels")
  
  input_length = get_sequence_length(inputs)

  lr = tf.Variable(FLAGS.initial_lr, trainable=False, name="lr")
  step = tf.Variable(0, trainable=False, name="global_step")

  w2v_model = KeyedVectors.load(FLAGS.embeddings_path, mmap='r')
  embedding_matrix = tf.Variable(
    w2v_model.syn0[:FLAGS.vocabulary_size],
    trainable=FLAGS.train_embeddings, name="embedding_matrix")
  embeddings = tf.nn.embedding_lookup(embedding_matrix, inputs)
  
  thought = build_encoder(embeddings, input_length)

  fw_logits = build_decoder(thought, fw_labels, embedding_matrix)
  bw_logits = build_decoder(thought, fw_labels, embedding_matrix,
                            name_id=1)
  
  # Mask the loss to avoid taking padding tokens into account.
  fw_mask = tf.sequence_mask(fw_length, FLAGS.max_length, dtype=tf.float32)
  bw_mask = tf.sequence_mask(bw_length, FLAGS.max_length, dtype=tf.float32)
  loss = seq2seq.sequence_loss(fw_logits, fw_labels, fw_mask) + \
         seq2seq.sequence_loss(bw_logits, bw_labels, bw_mask)

  # Adam optimizer with gradient clipping to prevent exploding gradients.
  tvars = tf.trainable_variables()
  grads, _ = tf.clip_by_global_norm(
    tf.gradients(loss, tvars), FLAGS.max_grad_norm)
  train_op = tf.train.AdamOptimizer(lr).apply_gradients(
    zip(grads, tvars), global_step=step)

  return inputs, fw_labels, bw_labels, thought, loss, lr, step, train_op


def sequences(fp):
  """Yield the integer id sentences from a file object."""
  sentence_buffer = []
  # Compensate for go token and the end-of-string token if requested.
  append_eos = not FLAGS.encode or FLAGS.eos_token
  max_length = FLAGS.max_length - 1
  if append_eos:
    max_length -= 1
  for line in fp:
    words = line.split()
    for word in words:
      sentence_buffer.append(...)
      if len(sentence_buffer) == max_length or word == '.':
        if append_eos:
          sentence_buffer.append(3)
        # Pad the sentence as a final step (id: 0).
        while len(sentence_buffer) < FLAGS.max_length:
          sentence_buffer.append(0)
        yield sentence_buffer
        sentence_buffer = []


def batches(seqs):
  """Yield batches given a sequence iterable."""
  batch_buffer = []
  for seq in seqs:
    batch_buffer.append(seq)
    if len(batch_buffer) == FLAGS.batch_size:
      yield batch_buffer
      batch_buffer = []
  # Check for remainder sentences and pad the rest of the batch.
  if len(batch_buffer) > 0:
    while len(batch_buffer) < FLAGS.batch_size:
      batch_buffer.append([0] * FLAGS.max_length)
    yield batch_buffer


if __name__ == '__main__':
  
  print("Building computational graph...")
  graph = tf.Graph()
  with graph.as_default():
    inputs, fw_l, bw_l, thought, loss, lr, step, train_op = build_model()

  with tf.Session(graph=graph) as sess:
    # Check if model can be restored
    saver = tf.train.Saver()
    output_dir = os.path.join('output', FLAGS.model_name)
    ckpt = tf.train.get_checkpoint_state(output_dir)
    if ckpt:
      print("Restoring model...")
      saver.restore(sess, ckpt.model_checkpoint_path)
      print("Restored model at step", sess.run(global_step))
    else:
      print("Initializing model...")
      sess.run(tf.global_variables_initializer())
      tf.gfile.MakeDirs(output_dir)
      print("Initialized model at", output_dir)

    # Inference
    if FLAGS.encode:
      with open(FLAGS.encode) as fp:
        for batch in batches(sequences(fp)):
          encoded_batch = sess.run(thought, feed_dict={inputs: batch})
          for v in encoded_batch:
            # The VEC string makes the resulting lines grep-able.
            print("VEC", *v)
  
    # Training
    else:
      for i in range(FLAGS.epochs):
        print("Entering epoch %d..." % i)
        file_list = os.listdir(FLAGS.dataset_path)
        random.shuffle(file_list)
        for filename in os.listdir(FLAGS.dataset_path):
          with open(filename) as fp:
            # TODO: can we find a way to not read the entire file?
            seqs = list(sequences(fp))
            # Since `batches` is a generator, this won't copy `seqs`
            in_batches = batches(seqs[1:-1])
            fw_batches = batches(seqs[2:])
            bw_batches = batches(seqs[:-2])
            for in_, fw, bw in zip(in_batches, fw_batches, bw_batches):
              step_loss, _ = sess.run(
                [loss, train_op], feed_dict={inputs: in_, fw_l: fw, bw_l: bw})
              print("Step", sess.run(step), "(loss={0:})")

