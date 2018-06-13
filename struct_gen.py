import numpy as np
import torch
import pdb
import math
from collections import defaultdict, deque


class Scope(object):
    def __init__(self, x_ori, y_ori, x_size, y_size):
        self.x_ori = x_ori
        self.y_ori = y_ori
        self.x_size = x_size
        self.y_size = y_size

        self.x_end = x_ori + x_size - 1
        self.y_end = y_ori + y_size - 1

        total_coord = [x_ori, y_ori, x_size, y_size]
        self.id = str(x_ori) + "_" + str(y_ori) + "_" + \
            str(x_size) + "_" + str(y_size)

class Leaf(object):
    def __init__(self, id):
        self.id = id

class PixelLeaf(Leaf):
    def __init__(self, x, y):
        id = str([x, y])
        super(PixelLeaf, self).__init__(id)
        self.x = x
        self.y = y
        self.depth = 0
        self.node_type = "Leaf"
        self.network_id = None

class BinaryLeaf(Leaf):
    def __init__(self, id):
        super(BinaryLeaf, self).__init__(id)

class Node(object):
    def __init__(self, scope, node_type=None):
        self.edges = []
        self.scope = scope
        self.depth = 0
        self.id = None
        self.node_type = node_type

class Edge(object):
    def __init__(self, parent=None, child=None):
        self.parent = parent
        self.child = child

class SumEdge(Edge):
    def __init__(self, parent=None, child=None, weight_id=None):
        Edge.__init__(self, parent=parent, child=child)
        self.weight_id = weight_id

class ProductEdge(Edge):
    def __init__(self, parent=None, child=None):
        Edge.__init__(self, parent=parent, child=child)

class Sum(Node):
    def __init__(self, scope=None):
        Node.__init__(self, scope, node_type="Sum")

class Product(Node):
    def __init__(self, scope=None):
        Node.__init__(self, scope, node_type="Product")

class GraphSPN(object):
    def __init__(self):
        self.roots = []

    def print_level_stat(self, level, level_type, level_nodes, edge_count):
        print("Level " + str(level) + " (" + level_type + ") : " + str(len(level_nodes)) + " nodes, " + str(edge_count) + " edges")

    def print_level_weight_indices(self, level, level_type, level_nodes, edge_count):
        if level_type != "Sum":
            return


        str_by_nodes = []
        for node in level_nodes:
            node_idx = list(node.weight_id_by_child.values())
            str_by_nodes.append( str(node_idx) )

        level_node_str = ''.join(str_by_nodes)

        print(level_node_str)

    def print_stat(self):
        self.traverse_by_level(self.print_level_stat)

    def print_weight_indices(self):
        self.traverse_by_level(self.print_level_weight_indices)

    def traverse_by_level(self, fn):
        '''
        :param fn: takes in #level, level type, nodes, edge_count
        :return:
        '''
        q = deque(self.roots)

        level = 0
        total_nodes = 0
        total_edges = 0
        visited = {}

        while q:
            level_size = len(q)
            node_count = 0
            edge_count = 0

            level_type = None
            level_nodes = []
            while level_size:
                u = q.popleft()
                level_nodes.append(u)
                level_size -= 1

                level_type = u.node_type

                node_count += 1

                if isinstance(u,PixelLeaf):
                    continue

                edge_count += len(u.edges)

                for e in u.edges:
                    v = e.child
                    if v in visited:
                        continue

                    q.append(v)
                    visited[v] = True

            total_nodes += node_count
            total_edges += edge_count

            fn(level, level_type, level_nodes, edge_count)

            level += 1

class CompleteSPN(GraphSPN):
    def __init__(self, num_variables, sum_factor, prd_factor):
        super(CompleteSPN, self).__init__()

        self.num_variables = num_variables
        self.sum_factor = sum_factor
        self.prd_factor = prd_factor

        self.roots = None
        self.leaves = []
        self.generate_structure()

    def generate_structure(self):
        self.roots = [self.generate_sum(0, self.num_variables - 1)]

    def generate_sum(self, start, end):
        scope_size = end - start + 1

        # If scope only contain a PixelLeaf, replace with a PixelLeaf node
        if scope_size == 1:
            leaf = PixelLeaf(0, 0)
            leaf.id = start
            leaf.network_id = 0
            return leaf

        # If scope contains multiple leaves, create a sum_node
        node = Sum()

        # Sum always have #sum_factor children
        for i in range(self.sum_factor):
            # Scope of its children are identical
            child_prd = self.generate_prd(start, end)
            node.children.append(child_prd)

        return node

    def generate_prd(self, start, end):
        node = Product()

        scope_size = end - start + 1

        # If we have less than #prd_factor leaves in our scope, then just
        # branch on whatever's remaining
        num_branches = min(scope_size, self.prd_factor)

        full_child_scope_size = math.ceil(scope_size / num_branches)
        remainder_child_scope_size = scope_size % full_child_scope_size

        # Generate the remainder children
        if remainder_child_scope_size > 0:
            child_start = end - remainder_child_scope_size + 1
            child_end = end
            child_sum = self.generate_sum(child_start, child_end)
            node.children.append(child_sum)

            # since we've generated the remainder, we have 1 less branch to generate
            num_branches -= 1

        # Generate the first #(num_branches - 1) children
        for i in range(num_branches):
            child_start = start + i * full_child_scope_size
            child_end = child_start + full_child_scope_size - 1
            child_sum = self.generate_sum(child_start, child_end)

            node.children.append(child_sum)

        return node

    def get_ordered_leaves(self, leaves):
        return leaves

class FlatSPN(object):
    def __init__(self, x_size, y_size):
        self.x_size = x_size
        self.y_size = y_size

        self.generate_spn()

    def generate_spn(self):
        root_scope = Scope(0, 0, self.x_size, self.y_size)
        self.roots = [Sum(root_scope)]

        for y in range(self.y_size):
            for x in range(self.x_size):
                child_leaf = PixelLeaf(x, y)
                self.roots[0].children.append(child_leaf)

class ConvSPN(GraphSPN):
    def __init__(self, x_size, y_size, sum_shifts, prd_subdivs):
        super(ConvSPN, self).__init__()

        self.x_size = x_size
        self.y_size = y_size
        self.sum_shifts = sum_shifts
        self.prd_subdivs = prd_subdivs

        self.weights = []

        self.cached_sum = {}
        self.cached_prd = {}
        self.cached_leaf = {}

        self.last_weight_id = -1

        # statistics
        self.depth = 0
        self.total_sum = 0
        self.total_prd = 0
        self.reused_sum = 0
        self.reused_prd = 0
        self.count_by_depth = defaultdict(int)

        self.generate_spn()

    def generate_spn(self):
        root_scope = Scope(0, 0, self.x_size, self.y_size)
        self.roots = [self.generate_sum(root_scope, 0)]

        num_weights = self.last_weight_id + 1
        self.weights = np.random.uniform(10, 1000, num_weights).astype('float32')

    def generate_leaf(self, scope, depth):
        if scope.id in self.cached_leaf:
            return self.cached_leaf[scope.id]

        leaf = PixelLeaf(scope.x_ori, scope.y_ori)
        leaf.depth = depth
        self.cached_leaf[scope.id] = leaf

        return leaf

    def generate_sum(self, scope, depth):
        self.total_sum += 1
        self.depth = max(self.depth, depth)
        child_depth = depth + 1

        # Check if we have a PixelLeaf node
        if scope.x_size == 1 and scope.y_size == 1:
            return self.generate_leaf(scope, child_depth)

        # Return cached sum if available
        cached_sum = self.get_cached_sum(scope)
        if cached_sum:
            self.reused_sum += 1
            return cached_sum

        # update statistics
        self.count_by_depth[depth] += 1

        # Generate root and all of its child products from shifts
        root = Sum(scope=scope)
        root.id = scope.id
        root.depth = depth

        shifts = self.generate_shifts(scope)

        for shift in shifts:
            prd = self.generate_prd(shift, child_depth)
            self.last_weight_id += 1

            edge = SumEdge(parent=root, child=prd, weight_id=self.last_weight_id)
            root.edges.append(edge)

        # Cache root
        self.cached_sum[scope.id] = root

        return root

    def generate_prd(self, scope, depth):
        self.total_prd += 1
        self.depth = max(self.depth, depth)
        child_depth = depth + 1

        # Return cached prd if available
        cached_prd = self.get_cached_prd(scope)
        if cached_prd:
            self.reused_prd += 1
            return cached_prd

        # update statistics
        self.count_by_depth[depth] += 1

        # Generate root and all of its child sums from subdivisions
        root = Product(scope=scope)
        root.id = scope.id
        root.depth = depth

        subdivs = self.generate_subdivisions(scope)

        for subdiv in subdivs:
            sum = self.generate_sum(subdiv, child_depth)

            edge = ProductEdge(parent=root, child=sum)

            root.edges.append(edge)

        # Cache root
        self.cached_prd[scope.id] = root

        return root

    def get_cached_sum(self, scope):
        if scope.id in self.cached_sum:
            return self.cached_sum[scope.id]

        return None

    def get_cached_prd(self, scope):
        if scope.id in self.cached_prd:
            return self.cached_prd[scope.id]

        return None

    def generate_shifts(self, scope):
        # sum_shifts
        '''
        To determine:
        - what is a reasonable shift?
        '''

        x_stride = math.ceil(float(scope.x_size) / float(self.sum_shifts))
        y_stride = math.ceil(float(scope.y_size) / float(self.sum_shifts))

        if x_stride == 0 or y_stride == 0:
            return []

        x_max = int(min(self.sum_shifts, scope.x_size))
        y_max = int(min(self.sum_shifts, scope.y_size))
        x_offsets = [i * x_stride for i in range(x_max)]
        y_offsets = [i * y_stride for i in range(y_max)]

        shifts = []
        for x_offset in x_offsets:
            for y_offset in y_offsets:
                shift = Scope(
                    scope.x_ori + x_offset,
                    scope.y_ori + y_offset,
                    scope.x_size,
                    scope.y_size)
                shifts.append(shift)

                '''
                Clips scope to parent's scope.
                The assumption wrt size ordering would be messed up, so matrix generation
                doesn't work as neat as we'd like it to be. Figure this out soon.
                '''
                # x_ori = scope.x_ori + x_offset
                # y_ori = scope.y_ori + y_offset
                #
                # # ensure that the end doesn't get out of the scope
                # x_end = min(scope.x_end, x_ori + scope.x_size - 1)
                # y_end = min(scope.y_end, y_ori + scope.y_size - 1)
                #
                # x_size = x_end - x_ori + 1
                # y_size = y_end - y_ori + 1
                #
                # shift = Scope(x_ori, y_ori, x_size, y_size)

        return shifts

    def scope_is_out_of_bounds(self, scope):
        # Get coordinates of all 4 corners
        a = (scope.x_ori, scope.y_ori)
        b = (scope.x_end, scope.y_ori)
        c = (scope.x_end, scope.y_end)
        d = (scope.x_ori, scope.y_end)

        corners = [a, b, c, d]

        # If any of the corner is inside the box, then the scope isn't out of bound
        for (x, y) in corners:
            if 0 <= x < self.x_size and 0 <= y < self.y_size:
                return False

        return True

    def generate_subdivisions(self, scope):
        '''
        for each subdivs
            pass if it's completely OOB, generate otherwise.
        '''

        x_size = math.ceil(float(scope.x_size) / float(self.prd_subdivs))
        y_size = math.ceil(float(scope.y_size) / float(self.prd_subdivs))

        if x_size == 0 or y_size == 0:
            return []

        x_max = int(min(self.prd_subdivs, scope.x_size))
        y_max = int(min(self.prd_subdivs, scope.y_size))
        x_offsets = [i * x_size for i in range(x_max)]
        y_offsets = [i * y_size for i in range(y_max)]

        subdivs = []
        for x_offset in x_offsets:
            for y_offset in y_offsets:
                subdiv = Scope(
                    scope.x_ori + x_offset,
                    scope.y_ori + y_offset,
                    x_size,
                    y_size)

                if self.scope_is_out_of_bounds(subdiv):
                    continue

                subdivs.append(subdiv)

        return subdivs

    def naive_traverse_by_level(self):
        '''
        Traverse the SPN as if subtree sharing isn't implemented. This would take too long on large SPNs.
        '''
        q = deque(self.roots)

        level = 0
        while q:
            level_size = len(q)
            all = []
            while level_size:
                u = q.popleft()
                level_size -= 1

                all.append(u.id)

                if isinstance(u,PixelLeaf):
                    continue
                for e in u.edges:
                    v = e.child
                    q.append(v)

            print("Level " + str(level) + ": " + str(len(all)))
            level += 1


class MultiChannelConvSPN(GraphSPN):
    def __init__(self, x_size, y_size, sum_shifts, prd_subdivs, num_channels, num_out):
        super(MultiChannelConvSPN, self).__init__()

        self.x_size = x_size
        self.y_size = y_size
        self.sum_shifts = sum_shifts
        self.prd_subdivs = prd_subdivs
        self.num_channels = num_channels
        self.num_out = num_out

        self.weights = []

        self.cached_prd = defaultdict(list)
        self.cached_leaf = defaultdict(list)

        # statistics
        self.depth = 0
        self.total_sum = 0
        self.total_prd = 0
        self.reused_sum = 0
        self.reused_prd = 0
        self.count_by_depth = defaultdict(int)

        self.generate_spn()

    def get_ordered_leaves(self, leaves):
        '''
        Orders the leaves to match input
        [input_channel_0, ..., input_channel_(k-1)]

        Where input_channel is row-ordered
        '''
        print("Ordering Leaves...")
        leaves_input_indices = []
        per_network_size = self.x_size * self.y_size
        for leaf in leaves:
            index_within_network = int(leaf.y) * self.x_size + int(leaf.x)
            index = (leaf.network_id * per_network_size) + index_within_network

            leaves_input_indices.append(index)

        leaf_index_pairs = zip(leaves, leaves_input_indices)
        leaf_index_pairs = sorted(leaf_index_pairs, key=lambda pair: pair[1])

        sorted_leaves = [pair[0] for pair in leaf_index_pairs]

        return sorted_leaves

    def generate_spn(self):
        '''
        1. Generate root
        2. Generate #num_channels ConvSPN
        3. Connect separate ConvSPN's sum node
        '''
        root_scope = Scope(0, 0, self.x_size, self.y_size)
        self.roots = []
        for i in range(self.num_out):
            self.roots.append(Sum(root_scope))

        channels = []
        for i in range(self.num_channels):
            channel = ConvSPN(self.x_size, self.y_size, self.sum_shifts, self.prd_subdivs)

            for leaf_scope in channel.cached_leaf:
                leaf = channel.cached_leaf[leaf_scope]
                leaf.network_id = i

            self.populate_cache_from_spn(channel)
            channels.append(channel)

        # Update sum node weight indices to
        offset = 0
        for channel in channels:
            self.weights.extend( channel.weights )

            update_fn = (lambda level, level_type, level_nodes, edge_count: self.channel_level_update(
                offset, level, level_type, level_nodes, edge_count))
            channel.traverse_by_level(update_fn)

            offset += len(self.weights)

        self.weights = np.array(self.weights)

        # Now, cache contains prd and leaves from all channels.
        # So now we add inter-channel connections.
        for channel in channels:
            self.add_interchannel_connection(channel)

        # Set channels as root's child and update channel's depth.
        offset = len(self.weights)
        num_root_edge = 0
        for root in self.roots:
            channel_children = channel.roots[0].edges

            root.edges = channel_children # all channel's root have identical children

            for c in channel_children:
                c.weight_id =  num_root_edge + offset
                num_root_edge += 1

        root_edge_weights = np.random.uniform(10, 1000, num_root_edge).astype('float32')

        self.weights = np.concatenate([ self.weights, root_edge_weights ])
        return
 
    def populate_cache_from_spn(self, spn):
        q = deque(spn.roots)
        visited = {}
        while q:
            level_size = len(q)

            while level_size:
                u = q.popleft()
                level_size -= 1

                if isinstance(u, Product):
                    self.cached_prd[u.scope.id].append(u)

                if isinstance(u, PixelLeaf):
                    self.cached_leaf[u.id].append(u)
                    continue

                for e in u.edges:
                    v = e.child
                    if v in visited:
                        continue

                    q.append(v)
                    visited[v] = True

    def add_interchannel_connection(self, spn):
        q = deque(spn.roots)
        visited = {}

        id_offset = len(self.weights)
        num_interchannel_edges = 0
        while q:
            level_size = len(q)

            while level_size:
                u = q.popleft()
                level_size -= 1

                if isinstance(u, PixelLeaf):
                    continue

                for e in u.edges:
                    v = e.child
                    if v in visited:
                        continue

                    q.append(v)
                    visited[v] = True

                if isinstance(u, Sum):
                    interchannel_children = []
                    old_children = [e.child for e in u.edges]
                    for v in old_children:
                        inter_child_in_v = self.cached_prd[v.scope.id]
                        interchannel_children.extend(inter_child_in_v)

                    new_children = list( set(interchannel_children) - set(old_children) )
                    for c in new_children:
                        weight_id = id_offset + num_interchannel_edges
                        edge = SumEdge(parent=u, child=c, weight_id=weight_id)
                        num_interchannel_edges += 1

                        u.edges.append(edge)

        interchannel_weights = np.random.uniform(10, 1000, num_interchannel_edges).astype('float32')
        self.weights = np.concatenate( [self.weights, interchannel_weights] )

    def channel_level_update(self, offset, level, level_type, level_nodes, edge_count):
        if level_type != "Sum":
            return

        for node in level_nodes:
            for e in node.edges:
                e.weight_id += offset

class ClassifierSPN(GraphSPN):
    def __init__(self, x_size, y_size, sum_shifts, prd_subdivs, num_channels, num_classes):
        super(ClassifierSPN, self).__init__()

        self.x_size = x_size
        self.y_size = y_size
        self.sum_shifts = sum_shifts
        self.prd_subdivs = prd_subdivs
        self.num_channels = num_channels
        self.num_classes = num_classes

        self.generate_spn()

    def generate_spn(self):
        root_scope = Scope(0, 0, self.x_size, self.y_size)
        root = Sum(root_scope)

        classes = []
        for c in range(num_classes):
            classifier = MultiChannelConvSPN(self.x_size, self.y_size, self.sum_shifts, self.prd_subdivs, self.num_channels)
            class_root = self.create_class_node(classifier, c)
            classes.append(class_root)

        root.children = classes

    def create_class_node(self, classifier, class_id):
        '''
        Create a product node with the class and its one-hot
        '''

        # note that it actually has an additional binary variable
        class_scope = Scope(0, 0, self.x_size, self.y_size)
        class_root = Product(class_scope)

        classifier_depth = classifier.depth

        binary_root = BinaryLeaf(class_id)
        binary_depth = 0
        empty_scope = Scope(0, 0, 0, 0)
        while binary_depth < classifier_depth:
            if binary_depth % 2 == 0:
                new_root = Product(empty_scope)
            else:
                new_root = Sum(empty_scope)

            new_root.children = [binary_root]
            binary_root = new_root

            binary_depth += 1

        class_root.children = [binary_root, classifier.root]

        return class_root


def overlap(scope1, scope2):
    '''
    Two scopes overlap if they have some common elements between them
    '''
    scope1 = list(map(int, scope1.split('_')))
    scope2 = list(map(int, scope2.split('_')))
    x_ori_1 = scope1[0]  # xo1
    x_end_1 = scope1[2]  # xe1
    y_ori_1 = scope1[1]  # yo1
    y_end_1 = scope1[3]  # ye1
    x_ori_2 = scope2[0]  # xo2
    x_end_2 = scope2[2]  # xe2
    y_ori_2 = scope2[1]  # yo2
    y_end_2 = scope2[3]  # ye2
    # Case 1: (xo1 <= xo2 <= xe1) && (yo1 <= yo2 <= ye1)
    if ((x_ori_1 <= x_ori_2 <= x_end_1) and (y_ori_1 <= y_ori_2 <= y_end_1)) or ((x_ori_2 <= x_ori_1 <= x_end_2) and (y_ori_2 <= y_ori_1 <= y_end_2)):
        return True
    # Case 2: (xo1 <= xe2 <= xe1) && (yo1 <= y02 <= ye1)
    elif ((x_ori_1 <= x_end_2 <= x_end_1) and (y_ori_1 <= y_ori_2 <= y_end_1)) or ((x_ori_2 <= x_end_1 <= x_end_2) and (y_ori_2 <= y_ori_1 <= y_end_2)):
        return True
    # Case 3: (xo1 <= xo2 <= xe1) && (yo1 <= ye2 <= ye1)
    elif ((x_ori_1 <= x_ori_2 <= x_end_1) and (y_ori_1 <= y_end_2 <= y_end_1)) or ((x_ori_2 <= x_ori_1 <= x_end_2) and (y_ori_2 <= y_end_1 <= y_end_2)):
        return True
    # Case 4: (xo1 <= xe2 <= xe1) && (yo1 <= ye2 <= ye1)
    elif ((x_ori_1 <= x_end_2 <= x_end_1) and (y_ori_1 <= y_end_2 <= y_end_1)) or ((x_ori_2 <= x_end_1 <= x_end_2) and (y_ori_2 <= y_end_1 <= y_end_2)):
        return True
    else:
        return False


def check_validity(root):
    '''
    checks the consistency and completeness of the SPN
    returns a tuple of id and True/False
    '''
    scope_hash = set()
    for child in root.children:
        if isinstance(child, PixelLeaf):
            if len(scope_hash) == 0:
                scope_hash.add(child.id)
            if root.node_type == 'Sum':
                if child.id not in scope_hash:
                    return -1, False
                else:
                    # prod
                    if child.id in scope_hash:
                        pdb.set_trace()
                        return -1, False
                    else:
                        scope_hash.add(child.id)
        else:
            child_id, valid_flag = check_validity(child)
            if valid_flag:
                if len(scope_hash) == 0:
                    scope_hash.add(child_id)
                if root.node_type == 'Sum':
                    if child_id not in scope_hash:
                        return -1, False
                else:
                    for scope in scope_hash:
                        if overlap(child_id, scope):
                            pdb.set_trace()
                            return -1, False
                        else:
                            scope_hash.add(child_id)
            else:
                return (-1, False)
    return root.id, True
