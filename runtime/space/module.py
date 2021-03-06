from interface import Object, null
from builtin import signature
from rpython.rlib import jit
import space

class Cell:
    _attrs_ = []
    def getval(self):
        assert False, "abstract"

    def setval(self, value):
        assert False, "abstract"

class MutableCell(Cell):
    _attrs_ = ['slot']
    def __init__(self, slot):
        self.slot = slot

    def getval(self):
        return self.slot

    def setval(self, value):
        self.slot = value

class FrozenCell(Cell):
    _attrs_ = ['slot']
    _immutable_fields_ = ['slot']
    def __init__(self, slot):
        self.slot = slot

    def getval(self):
        return self.slot

    def setval(self, value):
        assert False, "frozen"

class ShadowCell(Cell):
    _attrs_ = ['slot', 'link']
    _immutable_fields_ = ['link?']  # Accessing a parent value and
    def __init__(self, slot, link): # then overwriting it is a rare operation.
        self.slot = slot
        self.link = link

    def getval(self):
        if self.link is None:
            return self.slot
        else:
            return self.link.getval()

    def setval(self, value):
        self.slot = value
        self.link = None

class Module(Object):
    _immutable_fields_ = ['extends', 'cells']
    def __init__(self, name, namespace, extends=None, frozen=False):
        self.extends = extends
        self.frozen = frozen
        self.name = name
        self.cells = {}
        self.setattr_force(u"doc", null)
        for name in namespace:
            self.setattr_force(name, namespace[name])

    @jit.elidable
    def lookup(self, name, to_set=False):
        if self.extends is None or to_set:
            return self.cells[name]
        try:
            return self.cells[name]
        except KeyError:
            link = self.extends.lookup(name)
            self.cells[name] = cell = ShadowCell(null, link)
            return cell

    def list_locals(self):
        out = []
        for name, cell in self.cells.items():
            if isinstance(cell, ShadowCell) and cell.link is not None:
                continue
            out.append(name)
        return out

    def listattr(self):
        listing = Object.listattr(self)
        for name, cell in self.cells.items():
            if isinstance(cell, ShadowCell) and cell.link is not None:
                continue
            listing.append(space.String(name))
        return listing

    @jit.look_inside
    def getattr(self, name):
        try:
            cell = jit.promote(self.lookup(name))
            return cell.getval()
        except KeyError:
            return Object.getattr(self, name)

    @jit.look_inside
    def setattr(self, name, value):
        if self.frozen:
            raise space.unwind(space.LFrozenError(self))
        try:
            cell = jit.promote(self.lookup(name, True))
            cell.setval(value)
        except KeyError:
            self.cells[name] = MutableCell(value)
        return value

    def setattr_force(self, name, value):
        try:
            cell = jit.promote(self.lookup(name, True))
            if isinstance(cell, FrozenCell):
                if name == u'doc' and cell.slot == null: # this is implicit set, so we allow it.
                    self.cells[name] = FrozenCell(value) # violates the elidable -rule.
                else:
                    raise space.unwind(space.LFrozenError(self))
            else:
                cell.setval(value)
        except KeyError:
            if self.frozen:
                self.cells[name] = FrozenCell(value)
            else:
                self.cells[name] = MutableCell(value)
        return value

    def repr(self):
        return u"<module %s>" % self.name

def importer_poststage(module):
    try:
        doc = module.getattr(u"doc")
    except space.Unwinder as unwind:
        pass # TODO: allow only LAttributeError
    else:
        doclink_traverse(module, doc, null)

def doclink_traverse(obj, doc, parent):
    listing = obj.listattr()
    for name in listing:
        name = space.cast(name, space.String, u"importer poststage")
        field = obj.getattr(name.string)
        try:
            if field.getattr(u"doc") == null:
                docref = DocRef(doc, name, parent)
                field.setattr(u"doc", docref)
                doclink_traverse(field, doc, docref)
        except space.Unwinder as unwind:
            pass # TODO: pass only LAttributeError

class DocRef(Object):
    def __init__(self, doc, name, parent):
        self.doc = doc
        self.name = name
        self.parent = parent

    def getattr(self, name):
        if name == u"link":
            return self.doc
        if name == u"name":
            return self.name
        if name == u"parent":
            return self.parent
        return Object.getattr(self, name)

    def listattr(self):
        listing = Object.listattr(self)
        listing.append(space.String(u"link"))
        listing.append(space.String(u"name"))
        listing.append(space.String(u"parent"))
        return listing

@DocRef.instantiator2(signature(Object, Object, Object, optional=1))
def DocRef_init(doc, name, parent):
    parent = null if parent is None else parent
    return DocRef(doc, name, parent)
