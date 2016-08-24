import re
import gzip
import numpy
from nltk.corpus import wordnet as wn

class DataProcessor(object):
    def __init__(self, word_syn_cutoff=2, syn_path_cutoff=5):
        self.word_syn_cutoff = word_syn_cutoff
        self.syn_path_cutoff = syn_path_cutoff

        self.thing_prons = ['it', 'which', 'that', 'this', 'what', 'these', 'itself', 'something', 'anything', 'everything'] # thing
        self.male_prons = ['he', 'him', 'himself'] # man.n.01
        self.female_prons = ['she', 'her', 'herself'] # woman.n.01
        self.people_prons = ['they', 'them', 'themselves', 'we', 'ourselves', 'yourselves'] # people.n.01, people.n.03
        self.person_prons = ['you', 'i', 'who', 'whom', 'whoever', 'anyone', 'everyone', 'myself', 'yourself'] # person.n.01
        self.word_hypernym_map = {}
        self.word_index = {"NONE": 0, "UNK": 1}
        self.synset_index = {"NONE": 0, "UNK": 1}
        self.reverse_word_index = {0: "NONE", 1: "UNK"}
        self.reverse_synset_index = {0: "NONE", 1: "UNK"}
        # Word and synset embeddings are dict: index -> vector
        self.word_singletons = set([])
        self.word_non_singletons = set([])
        self.conc_singletons = set([])
        self.conc_non_singletons = set([])
        self.numpy_rng = numpy.random.RandomState(12345)

    # TODO: Take a coarse-grained mapping file and implement the following function.
    def map_fine_to_coarse(self, syn_name):
        raise NotImplementedError
        
    def get_hypernyms_syn(self, syn, path_cutoff=None):
        if not path_cutoff:
            path_cutoff = self.syn_path_cutoff
        hypernyms = []
        # Select shortest hypernym path
        all_paths = syn.hypernym_paths()
        shortest_path = all_paths[0]
        for path in all_paths:
            if len(shortest_path) > len(path):
                shortest_path = path
        pruned_path = list(shortest_path) if path_cutoff == -1 or path_cutoff >= len(shortest_path) else [x for x in reversed(shortest_path)][:path_cutoff]
        hypernyms = [s.name() for s in pruned_path]
        return hypernyms

    def get_hypernyms_word(self, word, pos, syn_cutoff=-1):
        wrd_lower = word.lower()
        if not pos:
            syns = []
        else:
            syns = wn.synsets(wrd_lower, pos=pos)
        hypernyms = []
        if wrd_lower in self.thing_prons:
            syns += wn.synsets("thing", "n")
        elif wrd_lower in self.male_prons:
            syns += wn.synsets("man", "n")
        elif wrd_lower in self.female_prons:
            syns += wn.synsets("woman", "n")
        elif wrd_lower in self.people_prons:
            syns += wn.synsets("people", "n")
        elif wrd_lower in self.person_prons:
            syns += wn.synsets("person", "n")
        elif re.match('^[12][0-9]{3}$', word) is not None:
            # The argument looks like an year
            syns += wn.synsets("year", "n") + wn.synsets("number", "n")
        elif re.match('^[0-9]+[.,-]?[0-9]*', word) is not None:
            syns += wn.synsets("number", "n")
        if len(hypernyms) == 0:
            if len(syns) != 0:
                pruned_synsets = list(syns) if self.word_syn_cutoff == -1 else syns[:self.word_syn_cutoff]
                for syn in pruned_synsets:
                    hypernyms.append(self.get_hypernyms_syn(syn))
            else:
                hypernyms = [[word]]
        return hypernyms

    # TODO: Separate methods for returning word inds and conc inds
    def index_sentence(self, words, pos_tags, for_test, remove_singletons):
        word_inds = []
        conc_inds = []
        wn_pos_tags = []
        for pos_tag in pos_tags:
            if pos_tag.startswith("J"):
                wn_pos = "a"
            elif pos_tag.startswith("V"):
                wn_pos = "v"
            elif pos_tag.startswith("N"):
                wn_pos = "n"
            elif pos_tag.startswith("R"):
                wn_pos = "r"
            else:
                wn_pos = None
            wn_pos_tags.append(wn_pos)
        for word, wn_pos in zip(words, wn_pos_tags):
            word = word.lower()
            if (word, wn_pos) in self.word_hypernym_map:
                word_hyps = self.word_hypernym_map[(word, wn_pos)]
            else:
                word_hyps = self.get_hypernyms_word(word, wn_pos)
                self.word_hypernym_map[(word, wn_pos)] = word_hyps
            # Add to singletons or non-singletons
            if word not in self.word_non_singletons:
                if word in self.word_singletons:
                    self.word_singletons.remove(word)
                    self.word_non_singletons.add(word)
                else:
                    self.word_singletons.add(word)
            for sense_syns in word_hyps:
                for syn in sense_syns:
                    if syn not in self.conc_non_singletons:
                        if syn in self.conc_singletons:
                            self.conc_singletons.remove(syn)
                            self.conc_non_singletons.add(syn)
                        else:
                            self.conc_singletons.add(syn)
        for word, wn_pos in zip(words, wn_pos_tags):
            word_conc_inds = []
            if word not in self.word_index and not for_test:
                if remove_singletons and word in self.word_singletons:
                    self.word_index[word] = self.word_index['UNK']
                else:
                    self.word_index[word] = len(self.word_index)
            word_hyps = self.word_hypernym_map[(word, wn_pos)]
            for sense_syns in word_hyps:
                word_sense_conc_inds = []
                # Most specific concept will be at the end
                for syn in reversed(sense_syns):
                    if syn not in self.synset_index and not for_test:
                        if remove_singletons and syn in self.conc_singletons:
                            self.synset_index[syn] = self.synset_index['UNK']
                        else:
                            self.synset_index[syn] = len(self.synset_index)
                    conc_ind = self.synset_index[syn] if syn in self.synset_index else self.synset_index['UNK']
                    word_sense_conc_inds.append(conc_ind)
                word_conc_inds.append(word_sense_conc_inds)
            word_ind = self.word_index[word] if word in self.word_index else self.word_index['UNK']
            word_inds.append(word_ind)
            conc_inds.append(word_conc_inds)
        return word_inds, conc_inds

    def pad_input(self, input_indices, onto_aware, sentlenlimit):
        # If onto aware, expected output shape is (num_sentences, num_words, num_senses, num_hyps)
        #   else, it is (num_sentences, num_words)
        # sentlenlimit is the limit used for padding all sentences to make them the same length.
        #   this applies only to the number of words. For senses and hyps, we'll use word_syn_cutoff 
        # and syn_path_cutoff
        # Recursive function!
        # Given unpadded input at any dimensionality, and a list of limits on lengths at all the 
        # following levels, pad the input appropriately.
        def _pad_struct(struct, limits, padding):
            '''
            struct: Unpadded nested input array
            limits: Lengths to pad the input to, at this level and all deeper levels of nesting.
                Eg.: If the input is a matrix, [[1,2], [3]], and we need three rows and two columns, 
                limits is [3, 2], and the output would be [[0, 0], [1,2], [0,3]]
            '''
            limit = limits[0]  # This level's limit
            # Adding padding at the current level
            for _ in range(limit - len(struct)):
                struct = [padding] + struct
            # Check if there are deeper levels
            if len(limits) > 1:
                return [_pad_struct(sub_struct, limits[1:], padding[0]) for sub_struct in struct]
            else:
                # If the input is already longer than limit, prune it.
                return struct[-limit:]
        if onto_aware:
            sent_limits = [sentlenlimit, self.word_syn_cutoff, self.syn_path_cutoff]
            sent_padding = [[0]]
        else:
            sent_limits = [sentlenlimit]
            sent_padding = 0
        # We do not need to pad at the sentence level. That is, we don't have a fixed num of sentences.
        # So, we loop over sentences.
        padded_input = [_pad_struct(word_indices, sent_limits, sent_padding) for word_indices in input_indices]
        return padded_input

    def prepare_input(self, tagged_sentences, sentlenlimit=None, onto_aware=False, for_test=False,
            remove_singletons=False):
        # Read all sentences, prepare input for Keras pipeline.
        # onto_aware = True: output synset indices or vectors instead of those for words.
        maxsentlen, all_words, all_pos_tags = self.read_sentences(tagged_sentences)
        if not sentlenlimit:
            # Not limit was set. Let's make all sentences as long as the longest sentence.
            sentlenlimit = maxsentlen
        # sent_inds contains word inds if not onto_aware. Else, it will contain synset inds
        unpadded_sent_inds = []
        for words, pos_tags in zip(all_words, all_pos_tags):
            word_inds, syn_inds = self.index_sentence(words, pos_tags, for_test, remove_singletons)
            if onto_aware:
                unpadded_sent_inds.append(syn_inds)
            else:
                unpadded_sent_inds.append(word_inds)
        # Pad indices
        padded_sent_inds = self.pad_input(unpadded_sent_inds, onto_aware, sentlenlimit)

        sent_input = numpy.asarray(padded_sent_inds, dtype='int32')
        # Update reverse indices
        if onto_aware:
            self.reverse_synset_index = {ind: synset for synset, ind in self.synset_index.items()}
        else:
            self.reverse_word_index = {ind: word for word, ind in self.word_index.items()}
        return sent_input

    def prepare_paired_input(self, tagged_sentence_pairs, sentlenlimit=None, onto_aware=False, for_test=False,
            remove_singletons=False):
        # Use this method for tasks like textual entailment where the input is a pair of sentences.
        first_sentences, second_sentences = zip(*[sentence_pair.split(" ||| ") for sentence_pair in tagged_sentence_pairs])
        # Assuming the same encoder will be used for encoding both the inputs, Keras requires the lengths be same.
        # If sentlenlimit is not provided, let's make sure prepare_input receives the max of the two lengths.
        if sentlenlimit is None:
            sentlenlimit = max([len(sentence.split(" ")) for sentence in first_sentences + second_sentences])
        first_sentence_input = self.prepare_input(first_sentences, sentlenlimit=sentlenlimit, onto_aware=onto_aware,
                for_test=for_test, remove_singletons=remove_singletons)
        second_sentence_input = self.prepare_input(second_sentences, sentlenlimit=sentlenlimit, onto_aware=onto_aware, 
                for_test=for_test, remove_singletons=remove_singletons)
        # Returning a list to let Keras directly process it.
        return [first_sentence_input, second_sentence_input]

    def read_sentences(self, tagged_sentences):
        # Preprocessing: Separate sentences, and output different arrays for words and tags.
        num_sentences = len(tagged_sentences)
        all_words = []
        all_pos_tags = []
        maxsentlen = 0
        for tagged_sentence in tagged_sentences:
            words = []
            pos_tags = []
            # Expects each token to be a "_" separated combination of word and POS tag.
            for word_tag in tagged_sentence.split(" "):
                word, tag = word_tag.split("_")
                word = word.lower()
                words.append(word)
                pos_tags.append(tag)
            sentlen = len(words)
            if sentlen > maxsentlen:
                maxsentlen = sentlen
            all_words.append(words)
            all_pos_tags.append(pos_tags)
        return maxsentlen, all_words, all_pos_tags 

    def get_embedding_matrix(self, embedding_file, onto_aware):
        # embedding_file is a tsv with words on the first column and vectors on the
        # remaining. This will add to word_embedding if for_words is true, or else to 
        # synset embedding.
        # For words that do not have vectors, we sample from a uniform distribution in the
        # range of max and min of the word embedding.
        embedding_map = {}
        rep_max = -float("inf")
        rep_min = float("inf")
        for line in gzip.open(embedding_file):
            ln_parts = line.strip().split()
            if len(ln_parts) == 2:
                continue
            element = ln_parts[0]
            vec = numpy.asarray([float(f) for f in ln_parts[1:]])
            vec_max, vec_min = vec.max(), vec.min()
            if vec_max > rep_max:
                rep_max = vec_max
            if vec_min < rep_min:
                rep_min = vec_min
                embedding_map[element] = vec
        embedding_dim = len(vec)
        target_index = self.synset_index if onto_aware else self.word_index
        # Initialize target embedding with all random vectors
        target_vocab_size = self.get_vocab_size(onto_aware=onto_aware)
        target_embedding = self.numpy_rng.uniform(low=rep_min, high=rep_max, size=(target_vocab_size, embedding_dim))
        for element in target_index:
            if element in embedding_map:
                vec = embedding_map[element]
            target_embedding[target_index[element]] = vec
        return target_embedding

    def get_token_from_index(self, index, onto_aware=True):
        token = self.reverse_synset_index[index] if onto_aware else self.reverse_word_index[index]
        return token 
    
    def get_vocab_size(self, onto_aware=True):
        vocab_size = max(self.synset_index.values()) + 1 if onto_aware else max(self.word_index.values()) + 1
        return vocab_size
