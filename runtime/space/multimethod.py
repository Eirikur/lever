from builtin import Builtin, signature
from numbers import Integer
from interface import Object, null
from rpython.rlib import jit
from rpython.rlib.objectmodel import compute_hash, r_dict
from rpython.rlib.rarithmetic import intmask
from errors import OldError
import space

def eq_fn(this, other):
    if len(this) != len(other):
        return False
    for i in range(len(this)):
        if not this[i] is other[i]:
            return False
    return True

def hash_fn(this):
    mult = 1000003
    x = 0x345678
    z = len(this)
    for item in this:
        y = compute_hash(item)
        x = (x ^ y) * mult
        z -= 1
        mult += 82520 + z + z
    x += 97531
    return intmask(x)

class Multimethod(Object):
    _immutable_fields_ = ['arity', 'multimethod_table']
    def __init__(self, arity, default=null):
        self.arity = arity
        self.multimethod_table = r_dict(eq_fn, hash_fn, force_non_null=True)
        self.default = default

    def call(self, argv):
        return self.invoke_method(argv, suppress_default=False)

    def call_suppressed(self, argv):
        return self.invoke_method(argv, suppress_default=True)

    @jit.elidable
    def get_method(self, *interface):
        return self.multimethod_table.get(list(interface), None)

    @jit.unroll_safe
    def invoke_method(self, argv, suppress_default):
        self = jit.promote(self)
        if len(argv) < self.arity:
            raise OldError(u"expected at least %d arguments, got %d" % (self.arity, len(argv))) 
        if self.arity == 1:
            method = self.get_method(jit.promote(space.get_interface(argv[0])))
        elif self.arity == 2:
            method = self.get_method(
                jit.promote(space.get_interface(argv[0])),
                jit.promote(space.get_interface(argv[1])))
        elif self.arity == 3:
            method = self.get_method(
                jit.promote(space.get_interface(argv[0])),
                jit.promote(space.get_interface(argv[1])),
                jit.promote(space.get_interface(argv[2])))
        elif self.arity == 4:
            method = self.get_method(
                jit.promote(space.get_interface(argv[0])),
                jit.promote(space.get_interface(argv[1])),
                jit.promote(space.get_interface(argv[2])),
                jit.promote(space.get_interface(argv[3])))
        else:
            vec = []
            for i in range(self.arity):
                vec.append(space.get_interface(argv[i]))
            method = self.multimethod_table.get(vec, None)
        if method is None:
            vec = []
            for i in range(self.arity):
                vec.append(space.get_interface(argv[i]))
            if self.default is null or suppress_default:
                names = []
                for i in range(self.arity):
                    names.append(vec[i].name)
                raise OldError(u"no method for ["+u' '.join(names)+u"]")
            return self.default.call(argv)
        return method.call(argv)

    def multimethod(self, *spec):
        vec = list(cls.interface for cls in spec)
        def _impl_(fn):
            self.multimethod_table[vec] = Builtin(fn)
            return fn
        return _impl_

    def multimethod_s(self, *spec):
        def _impl_(fn):
            self.multimethod(*spec)(signature(*spec)(fn))
            return fn
        return _impl_

    def getitem(self, index):
        index = space.cast(index, space.List, u"Multimethod.getitem")
        try:
            return self.multimethod_table[index.contents]
        except KeyError as _:
            raise space.unwind(space.LKeyError(self, index))

    def setitem(self, index, value):
        index = space.cast(index, space.List, u"Multimethod.setitem")
        vec = [
            space.cast(item,
                space.Interface,
                u"Multimethod expects interface list")
            for item in index.contents]
        self.multimethod_table[vec] = value
        return value

    def getattr(self, index):
        if index == u"default":
            return self.default
        return Object.getattr(self, index)

    def setattr(self, index, value):
        if index == u"default":
            self.default = value
            return value
        return Object.setattr(self, index, value)

@Multimethod.instantiator
@signature(Integer)
def _(arity):
    return Multimethod(arity.value)

@Multimethod.method(u"call_suppressed", signature(Multimethod, variadic=True))
def Multimethod_call_suppressed(mm, args):
    return mm.call_suppressed(args)

@Multimethod.method(u"keys", signature(Multimethod))
def Multimethod_keys(self):
    return space.List([
        space.List(list(vec))
        for vec in self.multimethod_table
    ])
