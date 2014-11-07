#Albert Cheu N15149196
#file system checker

#PRECONDITION: The blocks are in the same dir as this file
#PRECONDITION: We assume you can include serialize.py (by Cappos) via repypp.py

PREFIX = 'linddata.'
DEVID = 20
NOW = 1523630836
BLOCKSIZE = 4096
CONSTS = {'root':-1,'freeStart':-1,'freeEnd':-1,'numaccessible':-1}

include serialize.py

def getMetadata(blockNum):
    fname = PREFIX+str(blockNum)
    datafo = open(fname)#throws IO error if does not exist
    datastring = datafo.readline().strip()
    datafo.close()
    ans = deserializedata(datastring)

    #throw ValueError if not in right format, return otherwise

    if isinstance(ans, dict):
        #inode needs size field, superblock needs devId
        if 'size' not in ans and 'devId' not in ans:
            raise ValueError
            pass
        return ans

    if isinstance(ans, list):
        #index or f.b.l have only numbers
        for num in ans:
            if not isinstance(num, int): raise ValueError
            pass
        return ans

    raise ValueError
    

def prelimCheck(blockNums):
    print 'Running preliminary checks...'

    if len(blockNums) == 0 or blockNums[0] != 0:
        print 'There is no filesystem here'
        return False

    try:
        superblock = getMetadata(0)
    except:
        print 'Cannot deserialize superblock'
        return False
    CONSTS['root'] = superblock['root']
    CONSTS['freeStart'] = superblock['freeStart']
    CONSTS['freeEnd'] = superblock['freeEnd']
    #10,000 - superblock = 9,999
    CONSTS['numaccessible'] = superblock['maxBlocks'] - 1
    #9,999 - 25 (from free block list)
    CONSTS['numaccessible'] -= (CONSTS['freeEnd']-CONSTS['freeStart']+1)

    if superblock['creationTime'] >= NOW:
        print 'Superblock has an invalid creation time'
        return False
    elif superblock['devId'] != DEVID:
        print 'Superblock has an invalid device ID'
        return False
    
    for i in range(CONSTS['freeStart'],CONSTS['freeEnd']+1):
        #27 files must go from 0 to 26, no gaps/skips
        if i != blockNums[i]:
            print 'Missing block no.', i
            return False

        #Must be able to deserialize each file
        try: block = getMetadata(i)
        except:
            print 'Cannot deserialize block no.', i
            return False

        if not isinstance(block, list):
            print "Each entry of the free block list must be of type 'list'"
            return False

        pass

    #This looks okay.
    print 'Initial metadata look okay'
    return True

def checkFree(usedBlocks):
    print 'Checking if used blocks complement free blocks...'

    freeBlocks = set()
    for i in range(CONSTS['freeStart'],CONSTS['freeEnd']+1):
        fbl = getMetadata(i)
        for blockNum in fbl: freeBlocks.add(blockNum)
        pass

    #The free block list must not have anything that is used
    ntrsct = usedBlocks & freeBlocks 
    a = len(ntrsct) == 0
    #The list must also contain everything unused
    nn = usedBlocks | freeBlocks
    b = len(nn) == CONSTS['numaccessible']

    ans = a and b

    if ans: print 'Yes they do'
    else:
        if not a:
            print 'The free block list contains at least one used block'
            print ntrsct
            pass
        if not b:
            print 'The free block list is incomplete'
            print 'Used+Free should be %d blocks but currently have %d' % (CONSTS['numaccessible'],len(nn))
            pass
        pass

    return ans

def traverse():
    print 'Going through the file-system tree...'
    
    def checkDir(parentNum, thisNum, curPath, usedBlocks):
        print curPath

        try: inode = getMetadata(thisNum)
        except IOError as e:
            print 'Block', thisNum, 'has no associated file'
            return False
        except ValueError as e:
            print 'Cannot deserialize block no.', thisNum
            return False

        usedBlocks.add(thisNum)

        #Each directory contains . and .. and their block numbers are correct

        children = inode['filename_to_inode_dict']
        if 'd.' not in children:
            print "'.' not in inode"
            return False
        elif 'd..' not in children:
            print "'..' not in inode"
            return False
        elif thisNum != children['d.']:
            print "'.' does not refer to correct inode"
            return False
        elif parentNum != children['d..']:
            print "'..' does not refer to correct inode"
            return False
            
        #Each directory’s link count matches the number of links in the filename_to_inode_dict
        elif len(children) != inode['linkcount']:
            print "linkcount incorrect at block no.", thisNum
            return False

        #We have to go deeper!
        ans = True
        for child in children:
            if child[0]=='d' and child not in ('d.','d..'):
                ans = ans and checkDir(thisNum, children[child], curPath+child[1:]+'/', usedBlocks)
                pass
            elif child[0]=='f':
                ans = ans and checkFile(children[child], curPath+child[1:], usedBlocks)
                pass
            pass
        return ans

    def checkFile(blockNum, curPath, usedBlocks):
        print curPath

        try: inode = getMetadata(blockNum)
        except IOError as e:
            print 'Block', blockNum, 'has no associated file'
            return False
        except ValueError as e:
            print 'Cannot deserialize block no.', blockNum
            return False

        usedBlocks.add(blockNum)
        secondary = inode['location']

        try:
            #this code gets completed iff the indirect block is an index block
            index = getMetadata(secondary)
            usedBlocks.add(secondary)

            #If the data contained in a location pointer is an array, that indirect is one (True)
            if not inode['indirect']:
                print 'Inode', blockNum, 'is indirect but indirect field is set to False'
                return False

            ans = True
            for otherNum in index:
                #Do the files exist for these blocks?
                try: open(PREFIX+str(otherNum)).close()
                except IOError as e:
                    ans = False
                    print 'Block', otherNum, 'has no associated file'

                usedBlocks.add(otherNum)
                pass

            #Check size
            if (inode['size'] < (BLOCKSIZE*(len(index)-1))) or (inode['size'] > (BLOCKSIZE*len(index))):
                ans = False
                print 'Incorrect size for block no.', blockNum


            return ans

        except IOError as e:#happens when there is no file for this block
            print 'Block', secondary, 'has no associated file'
            return False

        except ValueError as e:#when the indirect block is raw data
            usedBlocks.add(secondary)
            if inode['indirect']:
                print 'Inode', blockNum, 'is not indirect but indirect field is set to True'
                return False

            #Check size                
            if inode['size'] > BLOCKSIZE:
                print 'Invalid size at block no.', blockNum
                return False

            return True

        return False #should never reach this!

    usedBlocks = set()
    b = checkDir(CONSTS['root'],CONSTS['root'],'/',usedBlocks)
    return b, usedBlocks

if callfunc == 'initialize':
    entries,blockNums = listdir(), []

    for e in entries:
        if e.startswith(PREFIX): blockNums.append(int(e[len(PREFIX):]))
        pass
    blockNums.sort()

    ok1 = prelimCheck(blockNums)

    if ok1:
        ok2,usedBlocks = traverse()
        if ok2: ok3 = checkFree(usedBlocks)
        pass

    if ok1 and ok2 and ok3:
        print "The file system is alright! Have a nice day, good sir or ma'am"
        pass
    else: print "Please fix the file system"
