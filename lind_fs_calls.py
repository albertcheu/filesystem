"""
  Author: Justin Cappos
  Module: File system calls for Lind.   This is essentially POSIX written in
          Repy V2.   

  Start Date: December 17th, 2011

  Modified by Albert Cheu, for homework
  10/11/14 - ?
"""
BLOCKSIZE = 4096
MAXBLOCKS = 10000
DEFAULT_TIME = 1323630836
NEW_TIME = 1423630836
DEVID = 20
PREFIX = 'linddata.'

#number of block numbers a block can point to
#used for free block list and index blocks
NUMNUM = 400

#Block 0
superblock = {}
SUPERBLOCKFNAME = PREFIX+'0'

#Blocks 1-25
STARTFREE, ENDFREE = 1,25
freeblocklist = []

#Blocks 26-9999
ROOTINODE = 26
rootblock = {}
ROOTBLOCKFNAME = PREFIX+str(ROOTINODE)
blocks = [rootblock]

# A lock that prevents inconsistencies
theLock = createlock()

# fast lookup table...
#maps [path from root] to [block number of inode (file or dir)]
path2inode = {}

# contains open file descriptor information... (keyed by fd)
filedescriptortable = {}

# contains file objects... (keyed by inode)
fileobjecttable = {}

# I use this so that I can assign to a global string
# without using global, which is blocked by RepyV2
currentDir = {'value':'/'}

#I want to see the errors!
SILENT=False

def warning(*msg):
  if not SILENT:
    for part in msg:
      print part,
    print


# This is raised to return an error...
class SyscallError(Exception):
  """A system call had an error"""


# This is raised if part of a call is not implemented
class UnimplementedError(Exception):
  """A call was called with arguments that are not fully implemented"""


def _load_lower_handle_stubs():
  """The lower file hadles need stubs in the descriptor talbe."""
  #stdin
  filedescriptortable[0] = {'position':0, 'inode':0, 'lock':createlock(), 'flags':O_RDWRFLAGS, 'note':'this is a stub1'}
  #stdout
  filedescriptortable[1] = {'position':0, 'inode':1, 'lock':createlock(), 'flags':O_RDWRFLAGS, 'note':'this is a stub2'}
  #stderr
  filedescriptortable[2] = {'position':0, 'inode':2, 'lock':createlock(), 'flags':O_RDWRFLAGS, 'note':'this is a stub3'}
  pass

def load_fs(name=SUPERBLOCKFNAME):
  """
  Help to correcly load a filesystem, if one exists, otherwise
  make a new empty one.  To do this, check if metadata exists.
  If it doesnt, call _blank_fs_init, if it DOES exist call restore_metadata

  This is the best entry point for programs loading the file subsystem.
  """
  try:
    # lets see if the metadata file is already here?
    f = openfile(name, False)
  except FileNotFoundError, e:
    warning("Note: No filesystem found, building a fresh one.")
    _blank_fs_init()
    load_fs_special_files()
  else:
    f.close()

    #load the blocks!
    for i in range(MAXBLOCKS):
      try: restore(PREFIX+str(i))
      except:
        warning(i)
        break
      pass
    superblock["mount"] += 1

    pass

  _load_lower_handle_stubs()


def load_fs_special_files():
  """ If called adds special files in standard locations.
  Specifically /dev/null, /dev/urandom and /dev/random
  """
  try: 
    mkdir_syscall("/dev", S_IRWXA)
  except SyscallError as e:
    warning( "making /dev failed. Skipping",str(e))

  # load /dev/null
  try:
    mknod_syscall("/dev/null", S_IFCHR, (1,3))
  except SyscallError as e:
    warning("making /dev/null failed. Skipping", str(e))

  # load /dev/urandom
  try:
    mknod_syscall("/dev/urandom", S_IFCHR, (1,9))
  except SyscallError as e:
    warning("making /dev/urandcom failed. Skipping",str(e))

  # load /dev/random
  try:
    mknod_syscall("/dev/random", S_IFCHR, (1,8))
  except SyscallError as e:
    warning("making /dev/random failed. Skipping", str(e))


# To have a simple, blank file system, simply run this block of code.
# 
def _blank_fs_init():

  # kill all left over data files...
  for filename in listfiles():
    if filename.startswith(PREFIX):
      removefile(filename)
      pass
    pass
  
  # Now setup blank data structures

  #superblock
  superblock['creationTime'] = DEFAULT_TIME
  superblock['mount'] = 0
  superblock['dev_id'] = DEVID
  superblock['root'] = ROOTINODE
  superblock['freeStart'] = STARTFREE
  superblock['freeEnd'] = ENDFREE
  superblock['maxBlocks'] = MAXBLOCKS
  persist(superblock,0)

  #root block
  rootblock['size'] = 0
  rootblock['uid'] = DEFAULT_UID
  rootblock['gid'] = DEFAULT_GID
  rootblock['mode'] = S_IFDIR | S_IRWXA # directory + all permissions
  rootblock['atime'] = DEFAULT_TIME
  rootblock['ctime'] = DEFAULT_TIME
  rootblock['mtime'] = DEFAULT_TIME
  rootblock['linkcount'] = 2 # the number of dir entries...
  rootblock['filename_to_inode_dict'] = {'d.':ROOTINODE,'d..':ROOTINODE}
  persist(rootblock,ROOTINODE)
  path2inode['/'] = ROOTINODE

  #freeblocklist
  #start right after root (means 27), end just before 400 (means 399)
  currentBlock,nextToHit = ROOTINODE+1,NUMNUM

  for i in range(ENDFREE - STARTFREE + 1):
    x = []
    for j in range(currentBlock,nextToHit):
      x.append(j)
      currentBlock += 1
      pass

    #second contains 400 to 799, etc.
    nextToHit += NUMNUM
    freeblocklist.append(x)

    #persist this block
    persist(x,i+1)
    pass    
  pass

def persist(block, blockNum):
  '''
  Very important function!
  Upon any change in metadata (superblock, freeblocklist, rootblock, inodes, indexes),
  call this function to preserve a specific block.
  '''
  fname = PREFIX+str(blockNum)
  datastring = serializedata(block)
  try: removefile(fname)
  except FileNotFoundError: pass
  datafo = openfile(fname,True)
  datafo.writeat(datastring,0)
  datafo.close()
  pass

def findBlockDetailed(blockNum):
  #return the block, the array it is in (if any), and its index in that array

  #the superblock is not in any array
  if blockNum == 0: block, targetArray, index = superblock, None, None

  #the root inode/dir is in the blocks array, at the first spot
  elif blockNum == ROOTINODE: block, targetArray, index = rootblock, blocks, 0

  else:
    #Free block list
    if blockNum >= STARTFREE and blockNum <= ENDFREE:
      targetArray, offset = freeblocklist, 1
      pass

    #Plain old block
    else:
      targetArray, offset = blocks, ROOTINODE
      #add to blocks if it isn't as big as we need
      #only happens when restore() is called, so no need to persist
      while len(blocks) <= (blockNum-offset): blocks.append({})
      pass

    index = blockNum - offset
    block = targetArray[index]
    pass

  return block, targetArray, index

#Just gimme the dictionary
def findBlock(blockNum): return findBlockDetailed(blockNum)[0]

def restore(fname):

  # open the file and write out the information...
  datafo = openfile(fname,True)
  datastring = datafo.readat(None, 0)
  datafo.close()

  # get what we stored
  try: data = deserializedata(datastring)
  #If we cannot deserialize, it means the block is "pure data" (a file)
  #which will be modified via syscalls (read/write/trunc, etc.)
  except: return

  dotIndex = fname.index('.')
  inode = int(fname[dotIndex+1:]) #block number
  block, targetArray, index = findBlockDetailed(inode)

  # should only be called with a fresh system...
  assert(block == {})

  if fname in (ROOTBLOCKFNAME, SUPERBLOCKFNAME):
    # I need to put things in the dict, but it's not a global...   so instead
    # add them one at a time.   It should be empty to start with
    for item in data: block[item] = data[item]
    pass
  else: targetArray[index] = data

  # I need to rebuild the path2inode table. let's do this!
  _rebuild_path2inode()
  pass

#path is already added.
def _rebuild_path2inode_helper(path, inode):
  # for each entry in my table...
  for entryname,entryinode in blocks[inode-ROOTINODE]['filename_to_inode_dict'].iteritems():
    if entryname in ('d.','d..'): continue

    # always add it... (clip off first character of entryname)
    entryPath = _get_absolute_path(path+'/'+entryname[1:])
    path2inode[entryPath] = entryinode

    # and recurse if a directory...
    if entryname[0] == 'd':
      _rebuild_path2inode_helper(entryPath,entryinode)
      pass
    pass

def _rebuild_path2inode():
  #first, empty it...
  for item in path2inode: del path2inode[item]
  #I need to add the root.   
  path2inode['/'] = ROOTINODE
  #recursively do the rest...
  _rebuild_path2inode_helper('', ROOTINODE)
  pass

######################   Generic Helper functions   #########################

#Find the (number of) next free block
def findNextFree():
  for i in range(ENDFREE-STARTFREE+1):
    if len(freeblocklist[i]) > 0:
      #take smallest element from the list (guaranteed to be first)
      blockNum = freeblocklist[i][0]
      del freeblocklist[i][0:1]
      #save change to f.b.l
      persist(freeblocklist[i], i+STARTFREE)
      #return the number
      return blockNum
    pass
  #If nothing free, we must do something!
  raise SyscallError("findNextFree","ENOFREE","No more free blocks!")

def allocate():
  #Create the dictionary for the block if necessary
  blockNum = findNextFree()
  while blockNum-ROOTINODE >= len(blocks): blocks.append({})
  #call persist in whatever calls this function (because it will do actual work)
  return blockNum

def freeBlock(blockNum):
  #free up the piece of memory that has this number
  x = freeblocklist[blockNum/NUMNUM] #27-399 are in 0, 400-799 are in 1, etc.
  #Add to the list of free blocks
  #runs in linear time... would be better if tree/heap were used
  #but we cant use modules (like Queue), which sucks
  loc = 0
  while x[loc] < blockNum: loc += 1
  x.insert(loc,blockNum)
  #we changed this metadata block, so save changes
  persist(x,loc+STARTFREE)
  pass

# private helper function that converts a relative path or a path with things
# like foo/../bar to a normal path.
def _get_absolute_path(path):
  
  if path == '': raise SyscallError('','ENOENT','There is no such thing as a nameless entry, dummy')

  # If it's a relative path, prepend the CWD...
  if path[0] != '/': path = currentDir['value'] + '/' + path

  #Splitting on '/' gives a list like: ['','foo','bar'] for '/foo/bar'
  pathlist = path.split('/')

  # let's remove the leading ''
  assert(pathlist[0] == '')
  pathlist = pathlist[1:]

  # Now, let's remove any '.' entries... (user input)
  while True:
    try: pathlist.remove('.')
    except ValueError: break
    pass

  # Also remove any '' entries...
  while True:
    try: pathlist.remove('')
    except ValueError: break
    pass

  # NOTE: This makes '/foo/bar/' -> '/foo/bar'.   I think this is okay.
  
  # for a '..' entry, remove the previous entry (if one exists).   This will
  # only work if we go left to right.
  position = 0
  while position < len(pathlist):
    if pathlist[position] == '..':
      # if there is a parent, remove it and this entry.  
      if position > 0:
        del pathlist[position]
        del pathlist[position-1]

        # go back one position and continue...
        position = position -1
        continue

      else:
        # I'm at the beginning.   Remove this, but no need to adjust position
        del pathlist[position]
        continue

    # it's a normal entry...   move along...
    else: position += 1

  # now let's join the pathlist!
  return '/'+'/'.join(pathlist)

# private helper function
def _get_absolute_parent_path(path):
  return _get_absolute_path(path+'/..')
 

#################### The actual system calls...   #############################


##### FSTATFS  #####

# return statfs data for fstatfs and statfs
def _istatfs_helper(inode):
  """
  """

  # I need to compute the amount of disk available / used
  limits, usage, stoptimes = getresources()

  # I'm going to fake large parts of this.   
  myfsdata = {}

  myfsdata['f_type'] = 0xBEEFC0DE   # unassigned.   New to us...

  myfsdata['f_bsize'] = BLOCKSIZE        # Match the repy V2 block size

  myfsdata['f_blocks'] = int(limits['diskused']) / BLOCKSIZE   

  myfsdata['f_bfree'] = (int(limits['diskused']-usage['diskused'])) / BLOCKSIZE  
  # same as above...
  myfsdata['f_bavail'] = (int(limits['diskused']-usage['diskused'])) / BLOCKSIZE  

  # file nodes...   I think this is infinite...
  myfsdata['f_files'] = 1024*1024*1024

  # free file nodes...   I think this is also infinite...
  myfsdata['f_files'] = 1024*1024*512

  myfsdata['f_fsid'] = superblock['dev_id']

  # we don't really have a limit, but let's say 254
  myfsdata['f_namelen'] = 254

  # same as blocksize...
  myfsdata['f_frsize'] = BLOCKSIZE 
  
  # it's supposed to be 5 bytes...   Let's try null characters...
  #CM: should be 8 bytes by my calc
  myfsdata['f_spare'] = '\x00'*8

  return myfsdata


def fstatfs_syscall(fd):
  """ 
    http://linux.die.net/man/2/fstatfs
  """
  # is the file descriptor valid?
  if fd not in filedescriptortable:
    raise SyscallError("fstatfs_syscall","EBADF","The file descriptor is invalid.")
  # if so, return the information...
  return _istatfs_helper(filedescriptortable[fd]['inode'])


##### STATFS  #####

def statfs_syscall(path):
  """ 
    http://linux.die.net/man/2/statfs
  """
  # in an abundance of caution, I'll grab a lock...
  theLock.acquire(True)

  # ... but always release it...
  try:
    truepath = _get_absolute_path(path)

    # is the path there?
    if truepath not in path2inode:
      raise SyscallError("statfs_syscall","ENOENT","The path does not exist.")

    thisinode = path2inode[truepath]
    
    return _istatfs_helper(thisinode)

  finally: theLock.release()

##### ACCESS  #####

def access_syscall(path, amode):
  """
    See: http://linux.die.net/man/2/access
  """
  try:
    # lock to prevent things from changing while we look this up...
    theLock.acquire(True)

    # get the actual name.   Remove things like '../foo'
    truepath = _get_absolute_path(path)

    if truepath not in path2inode:
      raise SyscallError("access_syscall","ENOENT","A directory in the path does not exist or file not found.")

    # BUG: This code should really walk the directories instead of using this 
    # table...   This will have to be fixed for symlinks to work.
    inode = path2inode[truepath]

    # BUG: This should take the UID / GID of the requestor in mind

    # if all of the bits for this file are set as requested, then success
    #if superblock['inodetable'][thisinode]['mode'] & amode == amode:
    if findBlock(inode)['mode'] & amode == amode:  return 0

    raise SyscallError("access_syscall","EACESS","The requested access is denied.")

  finally:
    #TODO: what must I persist? Isn't this just a check function?
    persist(superblock,0)

    # release the lock
    theLock.release()
    pass
  pass

##### CHDIR  #####

def chdir_syscall(path):
  """ 
    http://linux.die.net/man/2/chdir
  """
  # get the actual name.   Remove things like '../foo'
  truepath = _get_absolute_path(path)

  # If it doesn't exist...
  if truepath not in path2inode:
    raise SyscallError("chdir_syscall","ENOENT","A directory in the path does not exist.")

  # let's update and return success (0)
  currentDir['value'] = truepath
  return 0

##### MKDIR  #####

def mkdir_syscall(path, mode):
  """ 
    http://linux.die.net/man/2/mkdir
  """
  # lock to prevent things from changing while we look this up...
  theLock.acquire(True)

  # ... but always release it...
  try:
    if path == '':
      raise SyscallError("mkdir_syscall","ENOENT","Path does not exist.")

    truepath = _get_absolute_path(path)

    # is the path there?
    if truepath in path2inode:
      raise SyscallError("mkdir_syscall","EEXIST","The path exists.")
      
    # okay, it doesn't exist (great!). Does its parent exist and is it a dir?
    trueparentpath = _get_absolute_parent_path(path)

    if trueparentpath not in path2inode:
      raise SyscallError("mkdir_syscall","ENOENT","Parent path does not exist.")

    parentinode = path2inode[trueparentpath]
    parentBlock = findBlock(parentinode)

    if not IS_DIR(parentBlock['mode']):
      raise SyscallError("mkdir_syscall","ENOTDIR","Path's parent is not a directory.")

    # TODO: I should check permissions...
    assert(mode & S_IRWXA == mode)

    # okay, great!!!   We're ready to go!   Let's make the new name
    dirname = 'd'+truepath.split('/')[-1]

    #then, make the new directory...
    newinode = allocate()
    newinodeentry = {'size':0, 'uid':DEFAULT_UID, 'gid':DEFAULT_GID, 
            'mode':mode | S_IFDIR,  # DIR+rwxr-xr-x
            'atime':DEFAULT_TIME, 'ctime':DEFAULT_TIME, 'mtime':DEFAULT_TIME,
            'linkcount':2,    # the number of dir entries...
            'filename_to_inode_dict': {'d.':newinode, 'd..':parentinode}}
    blocks[newinode-ROOTINODE] = newinodeentry
    parentBlock['filename_to_inode_dict'][dirname] = newinode
    parentBlock['linkcount'] += 1

    #persist metadata changes
    persist(parentBlock, parentinode)
    persist(blocks[newinode-ROOTINODE],newinode)

    # finally, update the path2inode and return success!!!
    path2inode[truepath] = newinode    
    return 0

  finally: theLock.release()

##### RMDIR  #####

def rmdir_syscall(path):
  """ 
    http://linux.die.net/man/2/rmdir
  """

  # lock to prevent things from changing while we look this up...
  theLock.acquire(True)

  # ... but always release it...
  try:
    truepath = _get_absolute_path(path)

    # Is it the root?
    if truepath == '/':
      raise SyscallError("rmdir_syscall","EINVAL","Cannot remove the root directory.")
      
    # is the path there?
    if truepath not in path2inode:
      raise SyscallError("rmdir_syscall","EEXIST","The path does not exist.")

    thisinode = path2inode[truepath]
    
    # okay, is it a directory?
    if not IS_DIR(findBlock(thisinode)['mode']):
      raise SyscallError("rmdir_syscall","ENOTDIR","Path is not a directory.")

    # Is it empty?
    if findBlock(thisinode)['linkcount'] > 2:
      raise SyscallError("rmdir_syscall","ENOTEMPTY","Path is not empty.")

    # TODO: I should check permissions...
    trueparentpath = _get_absolute_parent_path(path)
    parentinode = path2inode[trueparentpath]
    parentBlock = findBlock(parentinode)

    # We're ready to go!   Let's clean up the file entry
    dirname = 'd'+truepath.split('/')[-1]

    # remove the entry from the parent...
    del parentBlock['filename_to_inode_dict'][dirname]

    # decrement the link count on the dir...
    parentBlock['linkcount'] -= 1

    #mark as free
    freeBlock(thisinode)

    persist(parentBlock, parentinode)
    #Don't persist thisinode, since the content hasn't changed

    # finally, clean up the path2inode and return success!!!
    del path2inode[truepath]

    return 0

  finally: theLock.release()


##### LINK  #####
def link_syscall(oldpath, newpath):
  """ 
    http://linux.die.net/man/2/link
  """

  # lock to prevent things from changing while we look this up...
  theLock.acquire(True)

  # ... but always release it...
  try:
    trueoldpath = _get_absolute_path(oldpath)

    # is the old path there?
    if trueoldpath not in path2inode:
      raise SyscallError("link_syscall","ENOENT","Old path does not exist.")

    oldinode = path2inode[trueoldpath]
    # is oldpath a directory?
    if IS_DIR(findBlock(oldinode)['mode']):
      raise SyscallError("link_syscall","EPERM","Old path is a directory.")
  
    # TODO: I should check permissions...

    # okay, the old path info seems fine...    
    if newpath == '':
      raise SyscallError("link_syscall","ENOENT","New path cannot exist.")

    truenewpath = _get_absolute_path(newpath)

    # does the newpath exist?   It shouldn't
    if truenewpath in path2inode:
      raise SyscallError("link_syscall","EEXIST","New path already exists.")
      
    # okay, it doesn't exist (great!). Does its parent exist and is it a dir?
    truenewparentpath = _get_absolute_parent_path(newpath)

    if truenewparentpath not in path2inode:
      raise SyscallError("link_syscall","ENOENT","New path's parent does not exist.")

    newparentinode = path2inode[truenewparentpath]
    if not IS_DIR(findBlock(newparentinode)['mode']):
      raise SyscallError("link_syscall","ENOTDIR","New path's parent is not a directory.")


    # TODO: I should check permissions...

    # okay, great!!!   We're ready to go!   Let's make the file...
    newfilename = 'f'+truenewpath.split('/')[-1]
    oldBlock, newParentBlock = findBlock(oldinode), findBlock(newparentinode)

    # first, make the directory entry...
    newParentBlock['filename_to_inode_dict'][newfilename] = oldinode

    # increment the link count on the dir...
    newParentBlock['linkcount'] += 1
    # ... and the file itself
    oldBlock['linkcount'] += 1

    persist(oldBlock, oldinode)
    persist(newParentBlock, newparentinode)

    # finally, update the path2inode and return success!!!
    path2inode[truenewpath] = oldinode    
    return 0

  finally: theLock.release()

##### UNLINK  #####
def unlink_syscall(path):
  """ 
    http://linux.die.net/man/2/unlink
  """

  # lock to prevent things from changing while we do this...
  theLock.acquire(True)

  # ... but always release it...
  try:
    truepath = _get_absolute_path(path)

    # is the path there?
    if truepath not in path2inode:
      raise SyscallError("unlink_syscall","ENOENT","The path does not exist.")
      
    thisinode = path2inode[truepath]
    
    # okay, is it a directory?
    if IS_DIR(findBlock(thisinode)['mode']):
      raise SyscallError("unlink_syscall","EISDIR","Path is a directory.")

    # TODO: I should check permissions...

    thisBlock = findBlock(thisinode)
    trueparentpath = _get_absolute_parent_path(path)
    parentinode = path2inode[trueparentpath]
    parentBlock = findBlock(parentinode)

    # We're ready to go!   Let's clean up the file entry
    dirname = 'f'+truepath.split('/')[-1]

    # remove the entry from the parent...
    del parentBlock['filename_to_inode_dict'][dirname]

    # decrement the link count on the dir...
    parentBlock['linkcount'] -= 1

    # clean up the path2inode
    del path2inode[truepath]

    # decrement the link count...
    thisBlock['linkcount'] -= 1

    # If zero, remove the entry from the inode table
    if thisBlock['linkcount'] == 0:
      #del superblock['inodetable'][thisinode]
      #UMMM...I THINK THIS IS RIGHT?
      freeBlock(thisinode)

      # TODO: I also would remove the file.   However, I need to do special
      # things if it's open, like wait until it is closed to remove it.
      pass

    persist(parentBlock, parentinode)
    persist(thisBlock, thisinode)

    return 0

  finally:
    persist(superblock,SUPERBLOCKFNAME)
    theLock.release()


##### STAT  #####
def stat_syscall(path):
  """ 
    http://linux.die.net/man/2/stat
  """
  # in an abundance of caution, I'll grab a lock...
  theLock.acquire(True)

  # ... but always release it...
  try:
    truepath = _get_absolute_path(path)

    # is the path there?
    if truepath not in path2inode:
      raise SyscallError("stat_syscall","ENOENT","The path does not exist.")

    thisinode = path2inode[truepath]
    
    # If its a character file, call the helper function.
    if IS_CHR(findBlock(thisinode)['mode']):
      return _istat_helper_chr_file(thisinode)
   
    return _istat_helper(thisinode)

  finally: theLock.release()


##### FSTAT  #####

def fstat_syscall(fd):
  """ 
    http://linux.die.net/man/2/fstat
  """
  # TODO: I don't handle socket objects.   I should return something like: 
  # st_mode=49590, st_ino=0, st_dev=0L, st_nlink=0, st_uid=501, st_gid=20, 
  # st_size=0, st_atime=0, st_mtime=0, st_ctime=0

  # is the file descriptor valid?
  if fd not in filedescriptortable:
    raise SyscallError("fstat_syscall","EBADF","The file descriptor is invalid.")

  # if so, return the information...
  inode = filedescriptortable[fd]['inode']
  if fd in [0,1,2] or \
    (filedescriptortable[fd] is filedescriptortable[0] or \
     filedescriptortable[fd] is filedescriptortable[1] or \
     filedescriptortable[fd] is filedescriptortable[2] \
    ):
    return (superblock['dev_id'],          # st_dev
          inode,                                 # inode
            49590, #mode
          1,  # links
          DEFAULT_UID, # uid
          DEFAULT_GID, #gid
          0,                                     # st_rdev     ignored(?)
          0, # size
          0,                                     # st_blksize  ignored(?)
          0,                                     # st_blocks   ignored(?)
          0,
          0,                                     # atime ns
          0,
          0,                                     # mtime ns
          0,
          0,                                     # ctime ns
        )
  if IS_CHR(findBlock(inode)['mode']):
    return _istat_helper_chr_file(inode)
  return _istat_helper(inode)

# private helper routine that returns stat data given an inode
def _istat_helper(inode):
  block = findBlock(inode)

  ret =  (superblock['dev_id'],          # st_dev
          inode,                                 # inode
          block['mode'],
          block['linkcount'],
          block['uid'],
          block['gid'],
          0,                                     # st_rdev     ignored(?)
          block['size'],
          0,                                     # st_blksize  ignored(?)
          0,                                     # st_blocks   ignored(?)
          block['atime'],
          0,                                     # atime ns
          block['mtime'],
          0,                                     # mtime ns
          block['ctime'],
          0,                                     # ctime ns
        )
  return ret

##### OPEN  #####
# get the next free file descriptor
def get_next_fd():
  # let's get the next available fd number.   The standard says we need to 
  # return the lowest open fd number.
  for fd in range(STARTINGFD, MAX_FD):
    if not fd in filedescriptortable:
      return fd
  raise SyscallError("open_syscall","EMFILE","The maximum number of files are open.")

def makeFileObject(inode):
  # if it exists, close the existing file object so I can remove it...
  if inode in fileobjecttable: fileobjecttable[inode].close()
  # remove the file...
  removefile(PREFIX+str(inode))
  # always open the file.
  fileobjecttable[inode] = openfile(PREFIX+str(inode),True)
  fileobjecttable[inode].writeat('\0'*BLOCKSIZE,0)
  pass

def open_syscall(path, flags, mode):
  """ 
    http://linux.die.net/man/2/open
  """
  # in an abundance of caution, lock...   I think this should only be needed
  # with O_CREAT flags...
  theLock.acquire(True)

  # ... but always release it...
  try:
    if path == '':
      raise SyscallError("open_syscall","ENOENT","The file does not exist.")

    truepath = _get_absolute_path(path)
    made = False

    # is the file missing?
    if truepath not in path2inode:

      # did they use O_CREAT? If not, throw error
      if not O_CREAT & flags:
        raise SyscallError("open_syscall","ENOENT","The file does not exist.")
      
      # okay, it doesn't exist (great!). Does its parent exist and is it a dir?
      trueparentpath = _get_absolute_parent_path(path)

      if trueparentpath not in path2inode:
        raise SyscallError("open_syscall","ENOENT","Path does not exist.")

      parentinode = path2inode[trueparentpath]
      if not IS_DIR(findBlock(parentinode)['mode']):
        raise SyscallError("open_syscall","ENOTDIR","Path's parent is not a directory.")

      # okay, great!!!   We're ready to go!   Let's make the new file...
      filename = truepath.split('/')[-1]

      # first, make the new file's entry...
      newinode = allocate()
      #we have one level of indirection
      secondaryNode = allocate()

      # be sure there aren't extra mode bits... No errno seems to exist for this.
      assert(mode & (S_IRWXA|S_FILETYPEFLAGS) == mode)
      effective_mode = (S_IFCHR | mode) if (S_IFCHR & flags) != 0 else (S_IFREG | mode)

      newinodeentry = {'size':0, 'uid':DEFAULT_UID, 'gid':DEFAULT_GID, 
                       'mode':effective_mode,
                       #initially assume we can fit data into one block, growing when necessary
                       'indirect':False, 'location': secondaryNode,
                       'atime':DEFAULT_TIME, 'ctime':DEFAULT_TIME, 'mtime':DEFAULT_TIME,
                       'linkcount':1}

      # ... and put it in the table..
      blocks[newinode-ROOTINODE] = newinodeentry
      
      # let's make the parent point to it...
      parentBlock = findBlock(parentinode)
      parentBlock['filename_to_inode_dict'][filename] = newinode
      # ... and increment the link count on the dir...
      parentBlock['linkcount'] += 1

      # finally, update the path2inode
      path2inode[truepath] = newinode

      # this file must not exist or it's an internal error!!!
      openfile(PREFIX+str(newinode),True).close()
      
      #We made a new file
      made = True

    # if the file did exist...
    else:
      # did they use O_CREAT and O_EXCL? If so, throw error
      if O_CREAT & flags and O_EXCL & flags:
        raise SyscallError("open_syscall","EEXIST","The file exists.")

      #If we are truncating the file, we are erasing before opening
      # If O_RDONLY is set, the behavior is undefined, so this is okay
      if O_TRUNC & flags:
        inode = path2inode[truepath]
        block = findBlock(inode)
        
        secondaryInode = block['location']#the block number of index block OR data
        secondaryBlock = findBlock(secondaryInode)#the actual index block OR data

        #Make file objects for all linddata.X that contain data
        #makeFileObject will destroy existing blocks and create blank replacements
        if block['indirect']:
          for loc in secondaryBlock['location']: makeFileObject(loc)
          pass
        else: makeFileObject(secondaryInode)

        # reset the size to 0
        block['size'] = 0
        pass

    # TODO: I should check permissions...
    # At this point, the file will exist... 

    # Let's find the inode
    inode = path2inode[truepath]
    block = findBlock(inode)

    # get the next fd so we can use it...
    thisfd = get_next_fd()
  
    # Note, directories can be opened (to do getdents, etc). We shouldn't
    # actually open something in this case...

    # Is it a regular file?
    if IS_REG(block['mode']):
      # this is a regular file. 
      #If the file never existed before this function call, store in f.o.t
      if made:
        dataBlockNum = block['location'] #we assumed the file fits in 1 block
        thisfo = openfile(PREFIX+str(dataBlockNum),False)
        fileobjecttable[dataBlockNum] = thisfo
        pass
      pass

    # I'm going to assume that if you use O_APPEND I only need to 
    # start the pointer in the right place.
    # else, let's start at the beginning
    position = block['size'] if (O_APPEND & flags) else 0

    # TODO handle read / write locking, etc.
    # Add the entry to the table!

    filedescriptortable[thisfd] = {'position':position, 'inode':inode, 'lock':createlock(), 'flags':flags&O_RDWRFLAGS}

    # Done!   Let's return the file descriptor.
    return thisfd

  finally: theLock.release()

##### CREAT  #####
def creat_syscall(pathname, mode):
  """ 
    http://linux.die.net/man/2/creat
  """
  try: return open_syscall(pathname, O_CREAT | O_TRUNC | O_WRONLY, mode)
  except SyscallError, e:
    # If it's a system call error, return our call name instead.
    assert(e[0]=='open_syscall')
    raise SyscallError('creat_syscall',e[1],e[2])

##### LSEEK  #####
def lseek_syscall(fd, offset, whence):
  """ 
    http://linux.die.net/man/2/lseek
  """
  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("lseek_syscall","EBADF","Invalid file descriptor.")

  # if we are any of the lower handles(stderr, sockets), cant seek, just report 0
  if filedescriptortable[fd]['inode'] in [0,1,2]: return 0

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)
  # ... but always release it...
  try:
    # we will need the file size in a moment, but also need to check the type
    try:
      inode = filedescriptortable[fd]['inode']
      block = findBlock(inode)
    except KeyError:
      raise SyscallError("lseek_syscall","ESPIPE","This is a socket, not a file.")
    
    # Let's figure out if this has a length / pointer...
    if IS_REG(block['mode']):
      # straightforward if it is a file...
      filesize = block['size']

    elif IS_DIR(block['mode']):
      # if a directory, let's use the number of entries
      filesize = len(block['filename_to_inode_dict'])

    else:
      # otherwise we don't know
      raise SyscallError("lseek_syscall","EINVAL","File descriptor does not refer to a regular file or directory.")

    # Figure out where we will seek to and check it...
    if whence == SEEK_SET:
      eventualpos = offset
    elif whence == SEEK_CUR:
      eventualpos = filedescriptortable[fd]['position']+offset
    elif whence == SEEK_END:
      eventualpos = filesize+offset
    else:
      raise SyscallError("lseek_syscall","EINVAL","Invalid whence.")

    # did we fall off the front?
    if eventualpos < 0:
      raise SyscallError("lseek_syscall","EINVAL","Seek before position 0 in file.")

    # did we fall off the back?
    # if so, we'll handle this when we do a write.   The correct behavior is
    # to write '\0' bytes between here and that pos.

    # do the seek and return success (the position)!
    filedescriptortable[fd]['position'] = eventualpos

    return eventualpos

  finally:
    # ... release the lock
    filedescriptortable[fd]['lock'].release()


##### READ  #####

def read_syscall(fd, count):
  """ 
    http://linux.die.net/man/2/read
  """

  # BUG: I probably need a filedescriptortable lock to prevent an untimely
  # close call or similar from messing everything up...

  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("read_syscall","EBADF","Invalid file descriptor.")

  # Is it open for reading?
  if IS_WRONLY(filedescriptortable[fd]['flags']): 
    raise SyscallError("read_syscall","EBADF","File descriptor is not open for reading.")

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)

  # ... but always release it...
  try:
    # get the inode so I can and check the mode (type)
    inode = filedescriptortable[fd]['inode']
    block = findBlock(inode)

    # If its a character file, call the helper function.
    if IS_CHR(block['mode']): return _read_chr_file(inode, count)

    # Is it anything other than a regular file?
    if not IS_REG(block['mode']):
      raise SyscallError("read_syscall","EINVAL","File descriptor does not refer to a regular file.")
      pass
      
    position = filedescriptortable[fd]['position']

    #If the block is direct, just do a simple read of the bytes
    if not block['indirect']: data = fileobjecttable[block['location']].readat(count,position)

    #If indirect...
    else:
      filesize = block['size']
      #throw error if you can't read that many bytes
      if filesize-position < count:
        raise SyscallError("read_syscall","foobar...","Can't read that many bytes from that position")
        pass

      data = ""
      #find which block to start from and the position within that block
      startIndex,modPosition = position / BLOCKSIZE, position % BLOCKSIZE
      blockNumbers = findBlock(block['location'])#a list of numbers
      for blockNum in blockNumbers[startIndex:]:
        #bytes left in this block
        bytesLeft = BLOCKSIZE - modPosition
        data += fileobjecttable[blockNum].readat(min(bytesLeft,count),modPosition)
        modPosition = 0
        count -= bytesLeft
        if count == 0: break
        pass
      pass

    # and update the position
    filedescriptortable[fd]['position'] += len(data)
    return data

  finally:
    # ... release the lock
    filedescriptortable[fd]['lock'].release()


##### WRITE  #####
def persistFile(block, blockNum):

  #persist index block if it exists
  if block['indirect']:
    indexLoc = block['location']
    persist(blocks[indexLoc-ROOTINODE],indexLoc)
    pass

  #persist file's inode
  persist(block,inode)
  pass


def write_syscall(fd, data):
  """ 
    http://linux.die.net/man/2/write
  """
  # BUG: I probably need a filedescriptortable lock to prevent an untimely
  # close call or similar from messing everything up...

  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("write_syscall","EBADF","Invalid file descriptor.")

  if filedescriptortable[fd]['inode'] in [0,1,2]:
    return len(data)

  # Is it open for writing?
  if IS_RDONLY(filedescriptortable[fd]['flags']): 
    raise SyscallError("write_syscall","EBADF","File descriptor is not open for writing.")

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)

  # ... but always release it...
  try:

    # get the inode so I can update the size (if needed) and check the type
    inode = filedescriptortable[fd]['inode']
    block = findBlock(inode)

    # If its a character file, call the helper function.
    if IS_CHR(block['mode']): return _write_chr_file(inode, data)

    # Is it anything other than a regular file?
    if not IS_REG(block['mode']):
      raise SyscallError("write_syscall","EINVAL","File descriptor does not refer to a regular file.")

    # let's get the position...
    position = filedescriptortable[fd]['position']
    if position < 0: raise SyscallError("write_syscall","foobar...","Please lseek to a positive number")
    
    #resize to fit our aims
    ftruncate_syscall(fd, position+len(data))

    #actually write the data
    if block['indirect']:
      #find which block to start from and the position within that block
      startIndex,modPosition = position / BLOCKSIZE, position % BLOCKSIZE
      index = findBlock(block['location'])
      lhs = 0
      for blockNumber in index[startIndex:]:
        #bytes left in this block
        bytesLeft = BLOCKSIZE - modPosition
        #write what needs to be written in this block -> which slice of data
        fileobjecttable[blockNumber].writeat(data[lhs:lhs+bytesLeft],modPosition)
        #shift the slice
        lhs += bytesLeft
        #subsequent blocks of data are written starting from the top
        modPosition = 0
        pass
      pass
    else: fileobjecttable[block['location']].writeat(data, position)

    # and update the position
    filedescriptortable[fd]['position'] += len(data)

    # update the file size if we've extended it
    if filedescriptortable[fd]['position'] > filesize:
      block['size'] = filedescriptortable[fd]['position']

    persistFile(block,inode)
      
    # we always write it all, so just return the length of what we were passed.
    # We do not mention whether we write blank data (if position is after the 
    # end)
    return len(data)

  finally:
    # ... release the lock
    filedescriptortable[fd]['lock'].release()


##### CLOSE  #####

# private helper.   Get the fds for an inode (or [] if none)
def _lookup_fds_by_inode(inode):
  returnedfdlist = []
  for fd in filedescriptortable:
    if not IS_SOCK_DESC(fd) and filedescriptortable[fd]['inode'] == inode:
      returnedfdlist.append(fd)
  return returnedfdlist

# is this file descriptor a socket? 
def IS_SOCK_DESC(fd):
  return 'domain' in filedescriptortable[fd]

# BAD this is copied from net_calls, but there is no way to get it
def _cleanup_socket(fd):
  if 'socketobjectid' in filedescriptortable[fd]:
    thesocket = socketobjecttable[filedescriptortable[fd]['socketobjectid']]
    thesocket.close()
    localport = filedescriptortable[fd]['localport']
    try:
      _release_localport(localport, filedescriptortable[fd]['protocol'])
    except KeyError:
      pass
    del socketobjecttable[filedescriptortable[fd]['socketobjectid']]
    del filedescriptortable[fd]['socketobjectid']
    
    filedescriptortable[fd]['state'] = NOTCONNECTED
    return 0

# private helper that allows this to be called in other places (like dup2)
# without changing to re-entrant locks
def _close_helper(fd):
  # if we are a socket, we dont change disk metadata
  if IS_SOCK_DESC(fd):
    _cleanup_socket(fd)
    return 0

  # get the inode for the filedescriptor
  inode = filedescriptortable[fd]['inode']
  block = findBlock(inode)
  # If it's not a regular file, we have nothing to close...
  if not IS_REG(block['mode']):
    # double check that this isn't in the fileobjecttable
    if inode in fileobjecttable:
      raise Exception("Internal Error: non-regular file in fileobjecttable")
       # and return success
    return 0

  # so it's a regular file.

  # get the list of file descriptors for the inode
  fdsforinode = _lookup_fds_by_inode(inode)

  # I should be in there!
  assert(fd in fdsforinode)

  # I should only close here if it's the last use of the file.   This can
  # happen due to dup, multiple opens, etc.
  if len(fdsforinode) > 1:
    # Is there more than one descriptor open?   If so, return success
    return 0

  # now let's close it and remove it from the table
  if block['indirect']:
    indexLoc = block['location']
    index = blocks[indexLoc-ROOTINODE]
    for blockNum in index:
      fileobjecttable[blockNum].close()
      del fileobjecttable[blockNum]
      pass
    pass

  else:
    fileobjecttable[block['location']].close()
    del fileobjecttable[block['location']]
    pass

  # success!
  return 0

def close_syscall(fd):
  """ 
    http://linux.die.net/man/2/close
  """
  # BUG: I probably need a filedescriptortable lock to prevent race conditions
  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("close_syscall","EBADF","Invalid file descriptor.")
  try:
    if filedescriptortable[fd]['inode'] in [0,1,2]:
      return 0
  except KeyError:
    pass
  # Acquire the fd lock, if there is one.
  if 'lock' in filedescriptortable[fd]:
    filedescriptortable[fd]['lock'].acquire(True)

  # ... but always release it...
  try:
    return _close_helper(fd)

  finally:
    # ... release the lock, if there is one
    if 'lock' in filedescriptortable[fd]:
      filedescriptortable[fd]['lock'].release()
    del filedescriptortable[fd]


##### DUP2  #####
# private helper that allows this to be used by dup
def _dup2_helper(oldfd,newfd):

  # if the new file descriptor is too low or too high
  # NOTE: I want to support dup2 being used to replace STDERR, STDOUT, etc.
  #      The Lind code may pass me descriptors less than STARTINGFD
  if newfd >= MAX_FD or newfd < 0:
    # BUG: the STARTINGFD isn't really too low.   It's just lower than we
    # support
    raise SyscallError("dup2_syscall","EBADF","Invalid new file descriptor.")

  # if they are equal, return them
  if newfd == oldfd: return newfd

  # okay, they are different.   If the new fd exists, close it.
  if newfd in filedescriptortable:
    # should not result in an error.   This only occurs on a bad fd 
    _close_helper(newfd)

  # Okay, we need the new and old to point to the same thing.
  # NOTE: I am not making a copy here!!!   They intentionally both
  # refer to the same instance because manipulating the position, etc.
  # impacts both.
  filedescriptortable[newfd] = filedescriptortable[oldfd]

  return newfd

def dup2_syscall(oldfd,newfd):
  """ 
    http://linux.die.net/man/2/dup2
  """
  # check the fd
  if oldfd not in filedescriptortable:
    raise SyscallError("dup2_syscall","EBADF","Invalid old file descriptor.")

  # Acquire the fd lock...
  filedescriptortable[oldfd]['lock'].acquire(True)

  # ... but always release it...
  try:
    return _dup2_helper(oldfd, newfd)

  # ... release the lock
  finally: filedescriptortable[oldfd]['lock'].release()


##### DUP  #####
def dup_syscall(fd):
  """ 
    http://linux.die.net/man/2/dup
  """

  # check the fd
  if fd not in filedescriptortable and fd >= STARTINGFD:
    raise SyscallError("dup_syscall","EBADF","Invalid old file descriptor.")

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)

  try: 
    # get the next available file descriptor
    try: nextfd = get_next_fd()
    except SyscallError, e:
      # If it's an error getting the fd, return our call name instead.
      assert(e[0]=='open_syscall')
    
      raise SyscallError('dup_syscall',e[1],e[2])
  
    # this does the work.   It should _never_ raise an exception given the
    # checks we've made...
    return _dup2_helper(fd, nextfd)

  # ... release the lock  
  finally: filedescriptortable[fd]['lock'].release()


##### FCNTL  #####
def fcntl_syscall(fd, cmd, *args):
  """ 
    http://linux.die.net/man/2/fcntl
  """
  # this call is totally crazy!   I'll just implement the basics and add more
  # as is needed.

  # BUG: I probably need a filedescriptortable lock to prevent race conditions

  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("fcntl_syscall","EBADF","Invalid file descriptor.")

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)

  # ... but always release it...
  try:
    # if we're getting the flags, return them... (but this is just CLO_EXEC, 
    # so ignore)
    if cmd == F_GETFD:
      if len(args) > 0:
        raise SyscallError("fcntl_syscall", "EINVAL", "Argument is more than\
          maximun allowable value.")
      return int((filedescriptortable[fd]['flags'] & FD_CLOEXEC) != 0)

    # set the flags...
    elif cmd == F_SETFD:
      assert(len(args) == 1)
      filedescriptortable[fd]['flags'] |= args[0]
      return 0

    # if we're getting the flags, return them...
    elif cmd == F_GETFL:
      assert(len(args) == 0)
      return filedescriptortable[fd]['flags']

    # set the flags...
    elif cmd == F_SETFL:
      assert(len(args) == 1)
      assert(type(args[0]) == int or type(args[0]) == long)
      filedescriptortable[fd]['flags'] = args[0]
      return 0

    # This is saying we'll get signals for this.   Let's punt this...
    elif cmd == F_GETOWN:
      assert(len(args) == 0)
      # Saying traditional SIGIO behavior...
      return 0

    # indicate that we want to receive signals for this FD...
    elif cmd == F_SETOWN:
      assert(len(args) == 1)
      assert(type(args[0]) == int or type(args[0]) == long)
      # this would almost certainly say our PID (if positive) or our process
      # group (if negative).   Either way, we do nothing and return success.
      return 0


    else:
      # This is either unimplemented or malformed.   Let's raise
      # an exception.
      raise UnimplementedError('FCNTL with command '+str(cmd)+' is not yet implemented.')

  finally:
    # ... release the lock
    filedescriptortable[fd]['lock'].release()


##### GETDENTS  #####
def getdents_syscall(fd, quantity):
  """ 
    http://linux.die.net/man/2/getdents
  """

  # BUG: I probably need a filedescriptortable lock to prevent race conditions

  # BUG BUG BUG: Do I really understand this spec!?!?!?!

  # check the fd
  if fd not in filedescriptortable:
    raise SyscallError("getdents_syscall","EBADF","Invalid file descriptor.")

  # Sanitizing the Input, there are people who would send other types too.
  if not isinstance(quantity, (int, long)):
    raise SyscallError("getdents_syscall","EINVAL","Invalid type for buffer size.")

  # This is the minimum number of bytes, that should be provided.
  if quantity < 24:
    raise SyscallError("getdents_syscall","EINVAL","Buffer size is too small.")

  # Acquire the fd lock...
  filedescriptortable[fd]['lock'].acquire(True)

  # ... but always release it...
  try:

    # get the inode so I can read the directory entries
    inode = filedescriptortable[fd]['inode']
    block = findBlock(inode)
    # Is it a directory?
    if not IS_DIR(block['mode']):
      raise SyscallError("getdents_syscall","EINVAL","File descriptor does not refer to a directory.")
      
    returninodefntuplelist = []
    bufferedquantity = 0

    # let's move the position forward...
    startposition = filedescriptortable[fd]['position']
    # return tuple with inode, name, type tuples...
    for entryname,entryinode in list(block['filename_to_inode_dict'].iteritems())[startposition:]:
      # getdents returns the mode also (at least on Linux)...
      entrytype = get_direnttype_from_mode(block['mode'])

      # Get the size of each entry, the size should be a multiple of 8.
      # The size of each entry is determined by sizeof(struct linux_dirent) which is 20 bytes plus the length of name of the file.
      # So, size of each entry becomes : 21 => 24, 26 => 32, 32 => 32.
      currentquantity = (((20 + len(entryname)) + 7) / 8) * 8

      # This is the overall size of entries parsed till now, if size exceeds given size, then stop parsing and return
      bufferedquantity += currentquantity
      if bufferedquantity > quantity:
        break

      returninodefntuplelist.append((entryinode, entryname, entrytype, currentquantity))

    # and move the position along.   Go no further than the end...
    filedescriptortable[fd]['position'] = min(startposition + len(returninodefntuplelist),\
      len(block['filename_to_inode_dict']))
    
    return returninodefntuplelist

  finally:
    # ... release the lock
    filedescriptortable[fd]['lock'].release()

#### CHMOD ####
def chmod_syscall(path, mode):
  """
    http://linux.die.net/man/2/chmod
  """
  # in an abundance of caution, I'll grab a lock...
  theLock.acquire(True)

  # ... but always release it...
  try:
    truepath = _get_absolute_path(path)

    # is the path there?
    if truepath not in path2inode:
      raise SyscallError("chmod_syscall", "ENOENT", "The path does not exist.")

    inode = path2inode[truepath]
    block = findBlock(inode)
    # be sure there aren't extra mode bits... No errno seems to exist for this
    assert(mode & (S_IRWXA|S_FILETYPEFLAGS) == mode)

    # should overwrite any previous permissions, according to POSIX.   However,
    # we want to keep the 'type' part of the mode from before
    block['mode'] = (block['mode'] & ~S_IRWXA) | mode
    persist(block,inode)

  finally: theLock.release()
  return 0

#### TRUNCATE  ####


def truncate_syscall(path, length):
  """
    http://linux.die.net/man/2/truncate
  """
  fd = open_syscall(path, O_RDWR, S_IRWXA)
  ret = ftruncate_syscall(fd, length)
  close_syscall(fd)
  return ret


#### FTRUNCATE ####
def ftruncate_syscall(fd, newsize, calledFromWrite=False):
  """
    http://linux.die.net/man/2/ftruncate
  """
  # check the fd
  if fd not in filedescriptortable and fd >= STARTINGFD:
    raise SyscallError("ftruncate_syscall","EBADF","Invalid old file descriptor.")

  if newsize < 0:
    raise SyscallError("ftruncate_syscall","EINVAL","Incorrect length passed.")

  # Acquire the fd lock (if called from anywhere but write_syscall, since that function locks already)
  if not calledFromWrite:
    desc = filedescriptortable[fd]
    desc['lock'].acquire(True)
    pass

  try: 
    # we will need the file size in a moment, but also need to check the type
    try: inode = desc['inode']
    except KeyError: raise SyscallError("lseek_syscall","ESPIPE","This is a socket, not a file.")

    #New size of the file must not exceed the limit
    if newsize > BLOCKSIZE*NUMNUM: raise SyscallError("ftruncate_syscall","EDQUOT","File too big")

    block = findBlock(inode)
    filesize = block['size']

    #How many blocks does the newsize need?
    neededBlocks = (newsize / BLOCKSIZE) + (1 if newsize % BLOCKSIZE else 0)

    #If new size of file is bigger than current one...
    if newsize > filesize:

      #direct stays as direct if the new size fits in one block
      #happily, unused bytes in the block are already \0
      if newsize <= BLOCKSIZE: pass

      else:
        #if we're a direct block, change to indirect
        if not block['indirect']:
          block['indirect'] = True
          #'location' slot in block now points to the index block
          #old data remains, but pointed to by the index block
          oldLoc = block['location']
          indexLoc = allocate()#where the index block will be
          block['location'] = indexLoc
          blocks[indexLoc-ROOTINODE] = [oldLoc]#index = list of numbers
          pass

        #Add needed blocks
        index = blocks[indexLoc-ROOTINODE]
        while len(index) < neededBlocks:
          index.append(allocate())
          makeFileObject(index[-1])#pre-filled with zeroes
          pass
        pass
      pass

    #Otherwise, no need to grow
    #clip off excess blocks
    elif block['indirect'] == True:
      indexLoc = block['location']
      index = findBlock(indexLoc)
      while len(index) > neededBlocks:
        freeBlock(index[-1])
        fileobjecttable[index[-1]].close()
        del fileobjecttable[index[-1]]
        index.pop()
        pass
      if len(index) == 1:
        block['indirect'] = False
        block['location'] = index[0]
        freeBlock(indexLoc)
        pass
      pass

    else: #newsize < filesize, and direct
      dataBlockNum = block['location']
      to_save = fileobjecttable[dataBlockNum].readat(newsize,0)
      fileobjecttable[dataBlockNum].close()
      # remove the old file
      removefile(PREFIX+str(inode))
      # make a new blank one
      fileobjecttable[dataBlockNum] = openfile(PREFIX+str(dataBlockNum),True)
      fileobjecttable[dataBlockNum].writeat(to_save, 0)
      pass
      
    block['size'] = new_len

    #persist changes (no need to do this if called from write)
    if not calledFromWrite: persistFile(block, inode)

  finally:
    if not calledFromWrite:
      desc = filedescriptortable[fd]
      desc['lock'].release() 
      pass
    pass

  return 0

#### MKNOD ####

# for now, I am considering few assumptions:
# 1. It is only used for creating character special files.
# 2. I am not bothering about S_IRWXA in mode. (I need to fix this).
# 3. /dev/null    : (1, 3)
#    /dev/random  : (1, 8)
#    /dev/urandom : (1, 9)
#    The major and minor device number's should be passed in as a 2-tuple.

def mknod_syscall(path, mode, dev):
  """
    http://linux.die.net/man/2/mknod
  """
  if path == '':
    raise SyscallError("mknod_syscall","ENOENT","The file does not exist.")

  truepath = _get_absolute_path(path)

  # check if file already exists, if so raise an error.
  if truepath in path2inode:
    raise SyscallError("mknod_syscall", "EEXIST", "file already exists.")

  # FIXME: mode should also accept user permissions(S_IRWXA)
  if not mode & S_FILETYPEFLAGS == mode: 
    raise SyscallError("mknod_syscall", "EINVAL", "mode requested creation\
      of something other than regular file, device special file, FIFO or socket")

  # FIXME: for now, lets just only create character special file 
  if not IS_CHR(mode):
    raise UnimplementedError("Only Character special files are supported.")

  # this has nothing to do with syscall, so I will raise UnimplementedError.
  if type(dev) is not tuple or len(dev) != 2:
    raise UnimplementedError("Third argument should be 2-tuple.")

  # Create a file, but don't open it. openning a chr_file should be done only using
  # open_syscall. S_IFCHR flag will ensure that the file is not opened.
  fd = open_syscall(path, mode | O_CREAT, S_IRWXA)

  # add the major and minor device no.'s, I did it here so that the code can be managed
  # properly, instead of putting everything in open_syscall.
  inode = filedescriptortable[fd]['inode']
  findBlock(inode)['rdev'] = dev
 
  # close the file descriptor... 
  close_syscall(fd)
  return 0


#### Helper Functions for Character Files.####
# currently supported devices are:
# 1. /dev/null
# 2. /dev/random
# 3. /dev/urandom

def _read_chr_file(inode, count):
  """
   helper function for reading data from chr_file's.
  """

  block = findBlock(inode)

  # check if it's a /dev/null. 
  if block['rdev'] == (1, 3):
    return ''
  # /dev/random
  elif block['rdev'] == (1, 8):
    return randombytes()[0:count]
  # /dev/urandom
  # FIXME: urandom is supposed to be non-blocking.
  elif block['rdev'] == (1, 9):
    return randombytes()[0:count]
  else:
    raise UnimplementedError("Given device is not supported.")


def _write_chr_file(inode, data):
  """
   helper function for writing data to chr_file's.
  """
  block = findBlock(inode)

  # check if it's a /dev/null.
  if block['rdev'] == (1, 3):
    return len(data)
  # /dev/random
  # There's no real /dev/random file, just vanish it into thin air.
  elif block['rdev'] == (1, 8):
    return len(data)
  # /dev/urandom
  # There's no real /dev/random file, just vanish it into thin air.
  elif block['rdev'] == (1, 9):
    return len(data)
  else:
    raise UnimplementedError("Given device is not supported.")


def _istat_helper_chr_file(inode):
  ret =  (5,          # st_dev, its always 5 for chr_file's.
          inode,                                 # inode
          block['mode'],
          block['linkcount'],
          block['uid'],
          block['gid'],
          block['rdev'],
          block['size'],
          0,                                     # st_blksize  ignored(?)
          0,                                     # st_blocks   ignored(?)
          block['atime'],
          0,                                     # atime ns
          block['mtime'],
          0,                                     # mtime ns
          block['ctime'],
          0,                                     # ctime ns
        )
  return ret

#### USER/GROUP IDENTITIES ####


def getuid_syscall():
  """
    http://linux.die.net/man/2/getuid
  """
  # I will return 1000, since this is also used in stat
  return DEFAULT_UID

def geteuid_syscall():
  """
    http://linux.die.net/man/2/geteuid
  """
  # I will return 1000, since this is also used in stat
  return DEFAULT_UID

def getgid_syscall():
  """
    http://linux.die.net/man/2/getgid
  """
  # I will return 1000, since this is also used in stat
  return DEFAULT_GID

def getegid_syscall():
  """
    http://linux.die.net/man/2/getegid
  """
  # I will return 1000, since this is also used in stat
  return DEFAULT_GID


#### RESOURCE LIMITS  ####

# FIXME: These constants should be specified in a different file, 
# it at all additional support needs to be added.
NOFILE_CUR = 1024
NOFILE_MAX = 4*1024

STACK_CUR = 8192*1024
STACK_MAX = 2**32

def getrlimit_syscall(res_type):
  """
    http://linux.die.net/man/2/getrlimit

    NOTE: Second argument is deprecated. 
  """
  if res_type == RLIMIT_NOFILE:
    return (NOFILE_CUR, NOFILE_MAX)
  elif res_type == RLIMIT_STACK:
    return (STACK_CUR, STACK_MAX)
  else:
    raise UnimplementedError("The resource type is unimplemented.")

def setrlimit_syscall(res_type, limits):
  """
    http://linux.die.net/man/2/setrlimit
  """

  if res_type == RLIMIT_NOFILE:
    # always make sure that, current value is less than or equal to Max value.
    if NOFILE_CUR > NOFILE_MAX:
      raise SyscallException("setrlimit", "EPERM", "Should not exceed Max limit.")

    # FIXME: I should update the value which should be per program.
    # since, Lind doesn't need this right now, I will pass.
    return 0

  else:
    raise UnimplementedError("This resource type is unimplemented")

#### FLOCK SYSCALL  ####

def flock_syscall(fd, operation):
  """
    http://linux.die.net/man/2/flock
  """
  if fd not in filedescriptortable:
    raise SyscallError("flock_syscall", "EBADF" "Invalid file descriptor.")

  # if we are anything besides the allowed flags, fail
  if operation & ~(LOCK_SH|LOCK_EX|LOCK_NB|LOCK_UN):
    raise SyscallError("flock_syscall", "EINVAL", "operation is invalid.")

  if operation & LOCK_SH:
    raise UnimplementedError("Shared lock is not yet implemented.")

  # check whether its a blocking or non-blocking lock...
  if operation & LOCK_EX and operation & LOCK_NB: 
    if filedescriptortable[fd]['lock'].acquire(False): 
      return 0
    else: # raise an error, if there's another lock already holding this
      raise SyscallError("flock_syscall", "EWOULDBLOCK", "Operation would block.")
  elif operation & LOCK_EX:
    filedescriptortable[fd]['lock'].acquire(True)
    return 0

  if operation & LOCK_UN:
    filedescriptortable[fd]['lock'].release()
    return 0

def rename_syscall(old, new):
  """
  http://linux.die.net/man/2/rename
  TODO: this needs to be fixed up.
  """
  theLock.acquire(True)
  try:
    true_old_path = _get_absolute_path(old)
    true_new_path = _get_absolute_path(new)

    if true_old_path not in path2inode:
      raise SyscallError("rename_syscall", "ENOENT", "Old file does not exist")

    if true_new_path == '':
      raise SyscallError("rename_syscall", "ENOENT", "New file does not exist")

    trueparentpath_old = _get_absolute_parent_path(true_old_path)
    parentinode = path2inode[trueparentpath_old]
    parentBlock = findBlock(parentinode)

    inode = path2inode[true_old_path]
    #block = findBlock(inode)
    
    newname = true_new_path.split('/')[-1]
    parentBlock['filename_to_inode_dict'][newname] = inode
    path2inode[true_new_path] = inode

    oldname = true_old_path.split('/')[-1]
    del parentBlock['filename_to_inode_dict'][oldname]
    del path2inode[true_old_path]

  finally:
    theLock.release()
  return 0
