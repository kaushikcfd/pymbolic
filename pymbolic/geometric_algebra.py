from __future__ import division

__copyright__ = "Copyright (C) 2009-2013 Andreas Kloeckner"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from pytools import memoize, memoize_method
from pymbolic.primitives import is_zero
import numpy as np




# {{{ helpers

def permutation_sign(p):
    p = list(p)
    s = +1

    for i in xrange(len(p)):
        # j is the current position of item I.
        j = i

        while p[j] != i:
            j += 1

        # Unless the item is already in the correct place, restore it.
        if j != i:
            p[i], p[j] = p[j], p[i]
            s = -s

    return s

def bit_count(i):
    """Count the number of set bits in *i*."""

    # nicked from http://wiki.python.org/moin/BitManipulation

    count = 0
    while i:
        i &= i - 1
        count += 1
    return count

def canonical_reordering_sign(a_bits, b_bits):
    """Count the number of basis vector swaps required to
    get the combination of 'a_bits' and 'b_bits' into canonical order.

    :arg a_bits: bitmap representing basis blade *a*
    :arg b_bits: bitmap representing basis blade *b*

    Algorithm from figure 19.1 of [DFM] in :class:`MultiVector`.
    """

    a_bits = a_bits >> 1
    s = 0
    while a_bits:
        s = s + bit_count(a_bits & b_bits)
        a_bits = a_bits >> 1;

    if s & 1:
        return -1
    else:
        return 1

# }}}

# {{{ space

class Space(object):
    """
    .. attribute :: basis_names

        A sequence of names of basis vectors.

    .. attribute :: metric_matrix

        A *(dims,dims)*-shaped matrix, whose *(i,j)*-th entry represents the
        inner product of basis vector *i* and basis vector *j*.
    """

    def __init__(self, basis=None, metric_matrix=None):
        """
        :arg basis: A sequence of names of basis vectors, or an integer (the
            number of dimensions) to use the default names ``e0`` through ``eN``.
        :arg metric_matrix: See :attr:`metric_matrix`.
            If *None*, the Euclidean metric is assumed.
        """

        if basis is None and metric_matrix is None:
            raise TypeError("at least one of 'basis' and 'metric_matrix' must be passed")

        if basis is None:
            basis = int(metric_matrix.shape[0])

        if isinstance(basis, int):
            basis = ["e%d" % i for i in xrange(basis)]

        if metric_matrix is None:
            metric_matrix = np.eye(len(basis), dtype=np.object)

        from pytools import all
        if not (
                len(metric_matrix.shape) == 2
                and
                all(dim == len(basis) for dim in metric_matrix.shape)):
            raise ValueError("metric_matrix has the wrong shape")

        self.basis_names = basis
        self.metric_matrix = metric_matrix

    @property
    def dimensions(self):
        return len(self.basis_names)

    def __getinitargs__(self):
        return (self.basis_names, self.metric_matrix)

    @memoize_method
    def bits_and_sign(self, basis_indices):
        # assert no repetitions
        assert len(set(basis_indices)) == len(basis_indices)

        sorted_basis_indices = tuple(sorted(
                (bindex, num)
                for num, bindex in enumerate(basis_indices)))
        blade_permutation = [num for bindex, num in sorted_basis_indices]

        bits = 0
        for bi in basis_indices:
            bits |= 2**bi

        return bits, permutation_sign(blade_permutation)

    @property
    @memoize_method
    def is_orthogonal(self):
        return (self.metric_matrix - np.diag(np.diag(self.metric_matrix)) == 0).all()

    @property
    @memoize_method
    def is_euclidean(self):
        return (self.metric_matrix == np.eye(self.mmat.shape[0])).all()

    def blade_bits_to_str(self, bits):
        return "^".join( 
                    name
                    for bit_num, name in enumerate(self.basis_names)
                    if bits & (1 << bit_num))

@memoize
def get_euclidean_space(n):
    """Return the canonical *n*-dimensional Euclidean :class:`Space`.
    """
    return Space(n)

# }}}

# {{{ blade product weights

def _shared_metric_coeff(shared_bits, space):
    result = 1

    basis_idx = 0
    while shared_bits:
        bit = (1 << basis_idx)
        if shared_bits & bit:
            result = result * space.metric_matrix[basis_idx, basis_idx]
            shared_bits ^= bit

        basis_idx += 1

    return result

class _GAProduct(object):
    pass

class _OuterProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        return int(not a_bits & b_bits)

    orthogonal_blade_product_weight = generic_blade_product_weight

class _GeometricProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        raise NotImplementedError("geometric product for spaces "
                "with non-diagonal metric (i.e. non-orthogonal basis)")

    @staticmethod
    def orthogonal_blade_product_weight(a_bits, b_bits, space):
        shared_bits = a_bits & b_bits

        if shared_bits:
            return _shared_metric_coeff(shared_bits, space)
        else:
            return 1

class _InnerProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        raise NotImplementedError("inner product for spaces "
                "with non-diagonal metric (i.e. non-orthogonal basis)")

    @staticmethod
    def orthogonal_blade_product_weight(a_bits, b_bits, space):
        shared_bits = a_bits & b_bits

        if shared_bits == a_bits or shared_bits == b_bits:
            return _shared_metric_coeff(shared_bits, space)
        else:
            return 0

class _LeftContractionProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        raise NotImplementedError("contraction product for spaces "
                "with non-diagonal metric (i.e. non-orthogonal basis)")

    @staticmethod
    def orthogonal_blade_product_weight(a_bits, b_bits, space):
        shared_bits = a_bits & b_bits

        if shared_bits == b_bits:
            return _shared_metric_coeff(shared_bits, space)
        else:
            return 0

class _RightContractionProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        raise NotImplementedError("contraction product for spaces "
                "with non-diagonal metric (i.e. non-orthogonal basis)")

    @staticmethod
    def orthogonal_blade_product_weight(a_bits, b_bits, space):
        shared_bits = a_bits & b_bits

        if shared_bits == a_bits:
            return _shared_metric_coeff(shared_bits, space)
        else:
            return 0

class _ScalarProduct(_GAProduct):
    @staticmethod
    def generic_blade_product_weight(a_bits, b_bits, space):
        raise NotImplementedError("contraction product for spaces "
                "with non-diagonal metric (i.e. non-orthogonal basis)")

    @staticmethod
    def orthogonal_blade_product_weight(a_bits, b_bits, space):
        if a_bits == b_bits:
            return _shared_metric_coeff(a_bits, space)
        else:
            return 0

# }}}

# {{{ multivector

class MultiVector(object):
    """An immutable multivector type. Implementation follows [DFM].

    .. attribute:: data

        A mapping from a basis vector bitmap indicating blades to coefficients.
        (see [DFM], Chapter 19 for the idea and rationale)

    The object behaves much like :class:`sympy.galgebra.GA.MV`, especially
    with respect to the supported operators.

    .. _ops_table:

    .. csv-table::
        :header: Operation, Result
        :widths: 10, 40

        ``A+B``,             Sum of multivectors
        ``A-B``,             Difference of multivectors
        ``A*B``,             Geometric product
        ``A^B``,             Outer product of multivectors
        ``A|B``,             Inner product of multivectors
        `A<<B``,             Left contraction of multivectors
        `A>>B``,             Right contraction of multivectors

        Table :ref:`1 <ops_table>`. :class:`Multi operations

    .. warning ::

        Many of the multiplicative operators bind more weakly than
        even *addition*. Python's operator precedence further does not
        match geometric algebra, which customarily evaluates outer, inner,
        and then geometric.

        In other words: Use parentheses everywhere.

    [DFM] L. Dorst, D. Fontijne, and S. Mann, Geometric Algebra for Computer
    Science: An Object-Oriented Approach to Geometry. Morgan Kaufmann, 2010.

    [HS] D. Hestenes and G. Sobczyk, Clifford Algebra to Geometric Calculus: A
    Unified Language for Mathematics and Physics. Springer, 1987.
    """

    # {{{ construction

    def __init__(self, data, space=None):
        """
        :arg data: This may be one of the following:
            1) a :class:`numpy.ndarray`, which will be turned into a grade-1 multivector,
            2) a mapping from tuples of basis indices (together indicating a blade,
            order matters and will be mapped to 'normalized' blades) to coefficients,
            3) an array as described in :attr:`data`,
            4) a scalar--where everything that doesn't fall into the above cases
               is viewed as a scalar.
        :arg space: A :class:`Space` instance. If *None* or an integer,
            :func:`get_euclidean_space` is called to obtain a default space with
            the right number of dimensions for *data*. Note: dimension guessing only
            works when :class:`numpy.ndarrays` are being passed for *data*.
        """

        dimensions = None

        if isinstance(data, np.ndarray):
            if len(data.shape) != 1:
                raise ValueError("only numpy vectors (not higher-rank objects) "
                        "are supported for 'data'")
            dimensions, = data.shape
            data = dict(
                    ((i,), xi) for i, xi in enumerate(data))
        elif isinstance(data, dict):
            pass
        else:
            data = {0: data}

        if space is None:
            space = get_euclidean_space(dimensions)
        else:
            if dimensions is not None and space.dimensions != dimensions:
                raise ValueError(
                        "dimension count of 'space' does not match that of 'data'")

        # {{{ normalize data to bitmaps, if needed

        from pytools import single_valued
        if data and single_valued(isinstance(k, tuple) for k in data.iterkeys()):
            # data is in non-normalized non-bits tuple form
            new_data = {}
            for basis_indices, coeff in data.iteritems():
                bits, sign = space.bits_and_sign(basis_indices)
                new_coeff = new_data.setdefault(bits, 0) + sign*coeff
                if is_zero(new_coeff):
                    del new_data[bits]
                else:
                    new_data[bits] = new_coeff

            data = new_data

        # }}}

        self.space = space
        self.data = data

    # }}}

    def __getinitargs__(self):
        return (self.data, self.space)

    mapper_method = "map_multi_vector"

    # {{{ stringification

    def __str__(self):
        if not self.data:
            return "0"

        terms = []
        for bits in sorted(self.data.iterkeys(),
                key=lambda bits: (bit_count(bits), bits)):
            coeff = self.data[bits]
            try:
                strifier = coeff.stringifier()
            except AttributeError:
                coeff_str = str(coeff)
            else:
                from pymbolic.mapper.stringifier import PREC_TIMES
                coeff_str = strifier(coeff, PREC_TIMES)

            blade_str = self.space.blade_bits_to_str(bits)
            if not blade_str:
                terms.append(coeff_str)
            else:
                terms.append("%s*%s" % (coeff_str, blade_str))

        return " + ".join(terms)

    # }}}

    # {{{ additive operators

    def __neg__(self):
        return MultiVector(
                dict((bits, -coeff)
                    for bits, coeff in self.data.iteritems()),
                self.space)

    def __add__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        if self.space is not other.space:
            raise ValueError("can only add multivectors from identical spaces")

        all_bits = set(self.data.iterkeys()) | set(other.data.iterkeys())

        new_data = {}
        for bits in all_bits:
            new_coeff = self.data.get(bits, 0) + other.data.get(bits, 0)
            if not is_zero(new_coeff):
                new_data[bits] = new_coeff

        return MultiVector(new_data, self.space)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        return self + (-other)

    def __rsub__(self, other):
        return other + (-self)

    # }}}

    # {{{ products

    def _generic_product(self, other, product_class):
        """
        :arg product_class: A subclass of :class:`_GAProduct`.
        """

        if self.space.is_orthogonal:
            bpw = product_class.orthogonal_blade_product_weight
        else:
            bpw = product_class.generic_blade_product_weight

        if self.space is not other.space:
            raise ValueError("can only compute products of multivectors "
                    "from identical spaces")

        new_data = {}
        for sbits, scoeff in self.data.iteritems():
            for obits, ocoeff in other.data.iteritems():
                new_bits = sbits ^ obits
                weight = bpw(sbits, obits, self.space)

                print self.space.blade_bits_to_str(sbits), self.space.blade_bits_to_str(obits)
                if not is_zero(weight):
                    # These are nonzero by definition.
                    coeff = weight * canonical_reordering_sign(sbits, obits) * scoeff * ocoeff
                    new_coeff = new_data.setdefault(new_bits, 0) + coeff
                    if is_zero(new_coeff):
                        del new_data[new_bits]
                    else:
                        new_data[new_bits] = new_coeff

        return MultiVector(new_data, self.space)

    def __mul__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _GeometricProduct)

    def __rmul__(self, other):
        return MultiVector(other, self.space) \
                ._generic_product(self, _GeometricProduct)

    def __xor__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _OuterProduct)

    def __rxor__(self, other):
        return MultiVector(other, self.space) \
                ._generic_product(self, _OuterProduct)

    def __or__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _InnerProduct)

    def __ror__(self, other):
        return MultiVector(other, self.space)\
                ._generic_product(self, _InnerProduct)

    def __lshift__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _LeftContractionProduct)

    def __rlshift__(self, other):
        return MultiVector(other, self.space)\
                ._generic_product(self, _LeftContractionProduct)

    def __rshift__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _RightContractionProduct)

    def __rrshift__(self, other):
        return MultiVector(other, self.space)\
                ._generic_product(self, _RightContractionProduct)

    def scalar_product(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self._generic_product(other, _ScalarProduct).as_scalar()

    # }}}

    def rev(self):
        """Return the *reverse* of *self*, i.e. the multivector obtained by reversing
        the order of all component blades.
        """
        new_data = {}
        for bits, coeff in self.data.iteritems():
            grade = bit_count(bits)
            if grade*(grade-1)//2 % 2 == 0:
                new_data[bits] = coeff
            else:
                new_data[bits] = -coeff

        return MultiVector(new_data, self.space)

    def invol(self):
        """Return the grade involution (see Section 2.9.5 of [DFM]), i.e.
        all odd-grade blades have their signs flipped.
        """
        new_data = {}
        for bits, coeff in self.data.iteritems():
            grade = bit_count(bits)
            if grade % 2 == 0:
                new_data[bits] = coeff
            else:
                new_data[bits] = -coeff

        return MultiVector(new_data, self.space)

    def norm_squared(self):
        return self.rev().scalar_product(self)

    def __abs__(self):
        return self.norm_squared()**0.5

    @property
    def I(self):
        return MultiVector({2**self.space.dimensions-1: 1}, self.space)

    # {{{ comparisons

    def __nonzero__(self):
        return bool(self.data)

    def __eq__(self, other):
        if not isinstance(other, MultiVector):
            other = MultiVector(other, self.space)

        return self.data == other.data

    def __ne__(self, other):
        return not self.__eq__(other)

    def zap_near_zeros(self, tol=None):
        # FIXME: Should use norm (or something) of self for tol.

        if tol is None:
            tol = 1e-13

        new_data = {}
        for bits, coeff in self.data.iteritems():
            if abs(coeff) > tol:
                new_data[bits] = coeff

        return MultiVector(new_data, self.space)

    def close_to(self, other, tol=None):
        return not (self-other).zap_near_zeros(tol=tol)

    # }}}

    # {{{ grade manipulation

    def project(self, grade):
        new_data = {}
        for bits, coeff in self.data.iteritems():
            if bit_count(bits) == grade:
                new_data[bits] = coeff

        return MultiVector(new_data, self.space)

    def get_pure_grade(self):
        """If *self* only has components of a single grade, return
        that as an integer. Otherwise, return *None*.
        """
        if not self.data:
            return 0

        result = None

        for bits, coeff in self.data.iteritems():
            grade = bit_count(bits)
            if result is None:
                result = grade
            elif result == grade:
                pass
            else:
                return None

        return result

    def as_scalar(self):
        result = 0
        for bits, coeff in self.data.iteritems():
            if bits != 0:
                raise ValueError("multivector is not a scalar")
            result = coeff

        return result

    def as_vector(self):
        result = [0] * self.space.dimensions
        log_table = dict((2**i, i) for i in xrange(self.space.dimensions))
        try:
            for bits, coeff in self.data.iteritems():
                result[log_table[bits]] = coeff
        except KeyError:
            raise ValueError("multivector is not a purely grade-1")

        return np.array(result)

    # }}}

# }}}

# vim: foldmethod=marker
