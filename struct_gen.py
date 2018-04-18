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
        self.id = str(x_ori) + "_" + str(y_ori) + "_" + str(x_size) + "_" + str(y_size)

class Leaf(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.depth = 0
        self.id = str([x,y])

class Node(object):
    def __init__(self, scope):
        self.children = []
        self.scope = scope
        self.depth = 0
        self.id = None

class Sum(Node):
    def __init__(self, scope):
        Node.__init__(self, scope)
        self.weights = []

class Product(Node):
    def __init__(self, scope):
        Node.__init__(self, scope)

class ConvSPN(object):
    def __init__(self, x_size, y_size, sum_shifts, prd_subdivs):
        self.x_size = x_size
        self.y_size = y_size
        self.sum_shifts = sum_shifts
        self.prd_subdivs = prd_subdivs

        self.root = None

        self.cached_sum = {}
        self.cached_prd = {}
        self.cached_leaf = {}

        # statistics
        self.depth = 0
        self.total_sum = 0
        self.total_prd = 0
        self.reused_sum = 0
        self.reused_prd = 0
        self.count_by_depth = defaultdict(int)

    def generate_spn(self):
        root_scope = Scope(0, 0, self.x_size, self.y_size)
        self.root = self.generate_sum(root_scope, 0)

    def generate_leaf(self, scope, depth):
        if scope.id in self.cached_leaf:
            return self.cached_leaf[scope.id]

        leaf = Leaf(scope.x_ori, scope.y_ori)
        leaf.depth = depth
        self.cached_leaf[scope.id] = leaf

        return leaf

    def generate_sum(self, scope, depth):
        self.total_sum += 1
        self.depth = max(self.depth, depth)
        child_depth = depth + 1

        # Check if we have a leaf node
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
        root = Sum(scope)
        root.id = scope.id
        root.depth = depth

        shifts = self.generate_shifts(scope)

        for shift in shifts:
            prd = self.generate_prd(shift, child_depth)
            root.children.append(prd)

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
        root = Product(scope)
        root.id = scope.id
        root.depth = depth

        subdivs = self.generate_subdivisions(scope)

        for subdiv in subdivs:
            sum = self.generate_sum(subdiv, child_depth)
            root.children.append(sum)

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

        x_max = min(self.sum_shifts, scope.x_size)
        y_max = min(self.sum_shifts, scope.y_size)
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

        x_max = min(self.prd_subdivs, scope.x_size)
        y_max = min(self.prd_subdivs, scope.y_size)
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

    def print_stat(self):
        # print("Reused sum: " + str(self.reused_sum) + "/" + str(self.total_sum))
        # print("Reused prd: " + str(self.reused_prd) + "/" + str(self.total_prd))
        #
        # for i in range(self.depth):
        #     c = self.count_by_depth[i]
        #     print("Depth " + str(i) + ": " + str(c) + " nodes")

        self.traverse_by_level()

    def traverse_by_level(self):
        q = deque([self.root])

        level = 0
        total_nodes = 0
        total_edges = 0
        while q:
            level_size = len(q)
            node_count = 0
            edge_count = 0

            visited = {}
            while level_size:
                u = q.popleft()
                level_size -= 1

                if isinstance(u, Leaf):
                    continue

                node_count += 1
                edge_count += len(u.children)

                for v in u.children:
                    if v in visited:
                        continue

                    q.append(v)
                    visited[v] = True

            total_nodes += node_count
            total_edges += edge_count
            print("Level " + str(level) + ": " + str(node_count) + " nodes, " + str(edge_count) + " edges")
            level += 1

        print(str(total_nodes) + " nodes")
        print(str(total_edges) + " edges")

    def naive_traverse_by_level(self):
        q = deque([self.root])

        level = 0
        while q:
            level_size = len(q)
            all = []
            while level_size:
                u = q.popleft()
                level_size -= 1

                all.append(u.id)

                if isinstance(u, Leaf):
                    continue
                for v in u.children:
                    q.append(v)

            print("Level " + str(level) + ": " + str(len(all)))
            level += 1

cv = ConvSPN(32, 32, 8, 2)
cv.generate_spn()

cv.print_stat()

pdb.set_trace()
