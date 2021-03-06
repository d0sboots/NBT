from struct import pack, unpack
from gzip import GzipFile

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10

class TAG(object):
	"""Each Tag needs to take a file-like object for reading and writing.
	The file object will be initialised by the calling code."""
	id = None

	def __init__(self, value=None, name=None):
		self.name = name
		self.value = value

	#Parsers and Generators
	def _parse_buffer(self, buffer):
		raise NotImplementedError(self.__class__.__name__)

	def _render_buffer(self, buffer, offset=None):
		raise NotImplementedError(self.__class__.__name__)

	#Printing and Formatting of tree
	def tag_info(self):
		return self.__class__.__name__ + \
               ('(%s)' % repr(self.name)) + \
               ": " + self.__repr__()

	def pretty_tree(self, indent=0):
		return ("\t"*indent) + self.tag_info()

class _TAG_Numeric(TAG):
	def __init__(self, unpack_as, size, value=None, name=None, buffer=None):
		super(_TAG_Numeric, self).__init__(value, name)
		self.unpack_as = unpack_as
		self.size = size
		if buffer:
			self._parse_buffer(buffer)

	#Parsers and Generators
	def _parse_buffer(self, buffer, offset=None):
		self.value = unpack(self.unpack_as, buffer.read(self.size))[0]

	def _render_buffer(self, buffer, offset=None):
		buffer.write(pack(self.unpack_as, self.value))

	#Printing and Formatting of tree
	def __repr__(self):
		return str(self.value)

class TAG_Byte(_TAG_Numeric):
	id = TAG_BYTE
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Byte, self).__init__(">b", 1, value, name, buffer)

class TAG_Short(_TAG_Numeric):
	id = TAG_SHORT
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Short, self).__init__(">h", 2, value, name, buffer)

class TAG_Int(_TAG_Numeric):
	id = TAG_INT
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Int, self).__init__(">i", 4, value, name, buffer)

class TAG_Long(_TAG_Numeric):
	id = TAG_LONG
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Long, self).__init__(">q", 8, value, name, buffer)

class TAG_Float(_TAG_Numeric):
	id = TAG_FLOAT
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Float, self).__init__(">f", 4, value, name, buffer)

class TAG_Double(_TAG_Numeric):
	id = TAG_DOUBLE
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_Double, self).__init__(">d", 8, value, name, buffer)

class TAG_Byte_Array(TAG):
	id = TAG_BYTE_ARRAY
	def __init__(self, buffer=None):
		super(TAG_Byte_Array, self).__init__()
		self.value = ''
		if buffer:
			self._parse_buffer(buffer)

	#Parsers and Generators
	def _parse_buffer(self, buffer, offset=None):
		length = TAG_Int(buffer=buffer)
		self.value = buffer.read(length.value)

	def _render_buffer(self, buffer, offset=None):
		length = TAG_Int(len(self.value))
		length._render_buffer(buffer, offset)
		buffer.write(self.value)

	#Printing and Formatting of tree
	def __repr__(self):
		return "[%i bytes]" % len(self.value)

class TAG_String(TAG):
	id = TAG_STRING
	def __init__(self, value=None, name=None, buffer=None):
		super(TAG_String, self).__init__(value, name)
		if buffer:
			self._parse_buffer(buffer)

	#Parsers and Generators
	def _parse_buffer(self, buffer, offset=None):
		length = TAG_Short(buffer=buffer)
		self.value = unicode(buffer.read(length.value), "utf-8")

	def _render_buffer(self, buffer, offset=None):
		save_val = self.value.encode("utf-8")
		length = TAG_Short(len(save_val))
		length._render_buffer(buffer, offset)
		buffer.write(save_val)

	#Printing and Formatting of tree
	def __repr__(self):
		return self.value

class TAG_List(TAG):
	id = TAG_LIST
	def __init__(self, type=None, value=None, name=None, buffer=None):
		super(TAG_List, self).__init__(value, name)
		if type:
			self.tagID = type.id
		else: self.tagID = None
		if buffer:
			self._parse_buffer(buffer)
		if not self.tagID:
			raise ValueError("No type specified for list")

	#Parsers and Generators
	def _parse_buffer(self, buffer, offset=None):
		self.tagID = TAG_Byte(buffer=buffer).value
		self.value = []
		length = TAG_Int(buffer=buffer)
		for x in range(length.value):
			self.value.append(TAGLIST[self.tagID](buffer=buffer))

	def _render_buffer(self, buffer, offset=None):
		TAG_Byte(self.tagID)._render_buffer(buffer, offset)
		length = TAG_Int(len(self.value))
		length._render_buffer(buffer, offset)
		for i, tag in enumerate(self.value):
			if tag.id != self.tagID:
				raise ValueError("List element %d(%s) has type %d != container type %d" %
						 (i, tag, tag.id, self.tagID))
			tag._render_buffer(buffer, offset)

	#Printing and Formatting of tree
	def __repr__(self):
		return "%i entries of type %s" % (len(self.tags), TAGLIST[self.tagID].__name__)

	def pretty_tree(self, indent=0):
		output = [super(TAG_List,self).pretty_tree(indent)]
		if len(self.tags):
			output.append(("\t"*indent) + "{")
			output.extend([tag.pretty_tree(indent+1) for tag in self.tags])
			output.append(("\t"*indent) + "}")
		return '\n'.join(output)

class TAG_Compound(TAG):
	id = TAG_COMPOUND
	def __init__(self, buffer=None):
		super(TAG_Compound, self).__init__()
		self.tags = []
		if buffer:
			self._parse_buffer(buffer)

	#Parsers and Generators
	def _parse_buffer(self, buffer, offset=None):
		while True:
			type = TAG_Byte(buffer=buffer)
			if type.value == TAG_END:
				#print "found tag_end"
				break
			else:
				name = TAG_String(buffer=buffer).value
				try:
					#DEBUG print type, name
					tag = TAGLIST[type.value](buffer=buffer)
					tag.name = name
					self.tags.append(tag)
				except KeyError:
					raise ValueError("Unrecognised tag type")

	def _render_buffer(self, buffer, offset=None):
		for tag in self.tags:
			TAG_Byte(tag.id)._render_buffer(buffer, offset)
			TAG_String(tag.name)._render_buffer(buffer, offset)
			tag._render_buffer(buffer,offset)
		buffer.write('\x00') #write TAG_END

	#Accessors
	def __getitem__(self, key):
		if isinstance(key,int):
			return self.tags[key]
		elif isinstance(key, str):
			for tag in self.tags:
				if tag.name == key:
					return tag
			else:
				raise KeyError("A tag with this name does not exist")
		else:
			raise ValueError("key needs to be either name of tag, or index of tag")


	#Printing and Formatting of tree
	def __repr__(self):
		return '%i Entries' % len(self.tags)

	def pretty_tree(self, indent=0):
		output = [super(TAG_Compound,self).pretty_tree(indent)]
		if len(self.tags):
			output.append(("\t"*indent) + "{")
			output.extend([tag.pretty_tree(indent+1) for tag in self.tags])
			output.append(("\t"*indent) + "}")
		return '\n'.join(output)


TAGLIST = {TAG_BYTE:TAG_Byte, TAG_SHORT:TAG_Short, TAG_INT:TAG_Int, TAG_LONG:TAG_Long, TAG_FLOAT:TAG_Float, TAG_DOUBLE:TAG_Double, TAG_BYTE_ARRAY:TAG_Byte_Array, TAG_STRING:TAG_String, TAG_LIST:TAG_List, TAG_COMPOUND:TAG_Compound}

class NBTFile(TAG_Compound):
	"""Represents an NBT file object"""

	def __init__(self, filename=None, mode=None, buffer=None):
		super(NBTFile,self).__init__()
		self.__class__.__name__ = "TAG_Compound"
		self.type = TAG_Byte(self.id)
		if filename:
			self.file = GzipFile(filename, mode)
		elif buffer:
			self.file = buffer
		else:
			self.file = None
		if self.file:
			self.parse_file(self.file)

	def parse_file(self, file=None):
		if not file:
			file = self.file
		if file:
			type = TAG_Byte(buffer=file)
			if type.value == self.id:
				name = TAG_String(buffer=file).value
				self._parse_buffer(file)
				self.name = name
				self.file.close()
			else:
				raise ValueError("First record is not a Compound Tag")
		else: ValueError("need a file!")

	def write_file(self, filename=None, buffer=None):
		if buffer:
			self.file = buffer
		elif filename:
			self.file = GzipFile(filename, "wb")
		elif not self.file:
			raise ValueError("Need to specify either a filename or a file")
		#Render tree to file
		TAG_Byte(self.id)._render_buffer(self.file)
		TAG_String(self.name)._render_buffer(self.file)
		self._render_buffer(self.file)
