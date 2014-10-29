#Albert Cheu N15149196
#file system checker

#PRECONDITION: The blocks are in the same dir as this file
#PRECONDITION: We assume serialize.py (by Cappos) is in same dir as this file

PREFIX = 'linddata.'
DEVID = 20
NOW = 1523630836
BLOCKSIZE = 4096

include serialize.py

def getMetadata(blockNum):
    fname = PREFIX+str(blockNum)
    datafo = open(fname)#throws IO error if does not exist
    datastring = datafo.readline().strip()
    datafo.close()
    return deserializedata(datastring)#throws ValueError if not in right format

def prelimCheck(blockNums):

    #every file system has superblock, free block list, and root inode
    if len(blockNums) < 27:
        print 'There is no filesystem here'
        return False

    for i in range(27):
        #27 files must go from 0 to 26
        if i != blockNums[i]:
            print 'Missing block no.', i
            return False

        #Must be able to deserialize each file

        try: getMetadata(i)
        except:
            print 'Cannot deserialize block no.', i
            return False
            
        #Superblock must be okay (time and device id)
        if i == 0:
            if block['creationTime'] >= NOW:
                print 'Superblock has an invalid creation time'
                return False
            elif block['dev_id'] != DEVID:
                print 'Superblock has an invalid device ID'
                return False
            pass

        elif i > 0 and i < 26:
            if not isinstance(block, list):
                print "Each entry of the free block list must be of type 'list'"
                return False
            pass

        pass

    #This looks okay.
    return True

def checkFree(usedBlocks):
    #free block = unreachable from root (and not in 0-25)
    #used block = reachable from root
    #we just compare usedBlocks to the info of the f.b.l (no overlap!)
    freeBlocks = set()
    for i in (1,26):
        fbl = getMetadata(i)
        for blockNum in fbl: freeBlocks.add(blockNum)
        pass
    return len(usedBlocks & freeBlocks) == 0

def traverse():
    #Go thru the file system
    
    def checkDir(parentNum, thisNum, usedBlocks):

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
            print "linkcount incorrect"
            return False

        #We have to go deeper!
        ans = True
        for child in children:
            if child.startswith('d') and child not in ('d.','d..'):
                ans = ans and checkDir(thisNum, child, usedBlocks)
                pass
            elif child.startswith('f'):
                ans = ans and checkFile(child, usedBlocks)
                pass
            pass
        return ans

    def checkFile(blockNum, usedBlocks):
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
                print 'Inode', blockNum 'is indirect but indirect field is set to False'
                return False

            ans = True
            for otherNum in index:
                #Do the files exist for these blocks?
                try: open(PREFIX+str(otherNum))
                except:
                    print 'Block', otherNum, 'has no associated file'
                    ans = False
                usedBlocks.add(otherNum)
                pass

            #Check size
            if inode['size'] < BLOCKSIZE*(len(index)-1) or inode['size'] >BLOCKSIZE*len(index):
                print 'Incorrect size for block no.', blockNum
                ans = False

            return ans

        except IOError as e:#happens when there is no file for this block
            print 'Block', secondary, 'has no associated file'
            return False

        except ValueError as e:#when the indirect block is raw data
            usedBlocks.add(secondary)
            if inode['indirect']:
                print 'Inode', blockNum 'is not indirect but indirect field is set to True'
                return False

            #Check size                
            if inode['size'] > BLOCKSIZE:
                print 'Invalid size at block no.', blockNum
                return False

            return True

        return False #should never reach this!

    usedBlocks = set()
    checkDir(26,26,usedBlocks)
    return True, usedBlocks

if callfunc == 'initialize':
    entries,blockNums = listdir(), []
    for e in entries:
        if e.startswith(PREFIX): blockNums.append(int(e[len(PREFIX):]))
        pass
    if prelimCheck(blockNums):
        ok,usedBlocks = traverse()
        if ok and checkFree(usedBlocks):
            print "The file system is alright! Have a nice day, good sir or ma'am"
            pass
        pass
    print "Please fix the file system"
