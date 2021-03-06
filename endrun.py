#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  endrun.py
#  
#  Copyright 2013 Grant Dobbe <grant@dobbe.us>
#  

import datetime, os, pickle, ConfigParser, git, shutil, hashlib, sqlite3, json
import warnings

# we suppress this because otherwise it fills the screen with tons of errors about a file in cache
with warnings.catch_warnings():
    '''Suppress this warning (for now?):
    /usr/local/lib/python2.7/dist-packages/cffi/vengine_cpy.py:166: UserWarning: reimporting '_cffi__xb217b92x9ad92d80' might overwrite older definitions
    % (self.verifier.get_module_name()))
    '''
    warnings.simplefilter("ignore")
    import nacl.utils, nacl.encoding, nacl.signing
    from nacl.public import PrivateKey, Box

NONCE_SIZE = 24

    
'''
Grab the config file (we're gonna need it later on)
'''
try:
  config = ConfigParser.ConfigParser()
  config.read(os.path.dirname(os.path.realpath(__file__)) + '/settings.conf')
  assert(config.get('global', 'nodename'))
except ConfigParser.NoSectionError:
  print "Your config file does not appear to be valid. Please verify that settings.conf exists and follows the syntax of settings.conf.sample"
  

'''
-----------------
Class declaration
-----------------
'''
class Payload:
  
  # ttl = the ISO Date and time for when the payload becomes invalid.
  ttl = datetime.datetime.now() + datetime.timedelta(hours=24)
  # origin - a unique identifier that can be used to pull up my public key
  origin = config.get('global', 'nodename')
  # destination - a unique identifier that can be used to pull up their private key
  destination = ''
  # nonce = a number used once for purposes of encryption and decryption
  nonce = nacl.utils.random(NONCE_SIZE)
  # payload - nacl encrypted git bundle 
  # empty by default
  payload = ''
  # custodychain - a json array containing the complete chain of custody for an endrun payload
  custodychain = []
  # copies - upper limit on number of copies that a node should send of this payload
  copies = 10
  
  def __init__(self):
    self.ttl = datetime.datetime.now() + + datetime.timedelta(hours=int(config.get('global', 'ttl')))
    self.origin = config.get('global', 'nodename')
    self.destination = ''
    self.nonce = nacl.utils.random(NONCE_SIZE)
    self.payload = ''
    
  # serializes whatever is fed to it
  def serialize(self, material):
    return pickle.dump(material)
    
  #deserializes whatever is fed to it
  def deserialize(self, material):
    return pickle.load(material)
  
  # encrypts data and saves it to the payload
  # args:
  #   payload_contents: binary data to be encrypted and assigned to the payload object
  def wrap(self, payload_contents ):
    # look up the signature key
    with open( config.get('global', 'keypath') + '/' + self.origin + '.sig', 'r') as originSigKey:
      originSig = self.deserialize(originSigKey)
    # look up the public and private keys
    with open( config.get('global', 'keypath') + '/' + self.origin + '.private', 'r' ) as originPrivateKey:
      originKey = self.deserialize(originPrivateKey)
    with open( config.get('global', 'keypath') + '/' + self.destination + '.public', 'r' ) as destinationPublicKey:
      destinationKey = self.deserialize(destinationPublicKey)
    # make payload a NaCL box
    container = Box( originKey, destinationKey )
    # sign the contents
    signedContents = originSig.sign(payload_contents)
    # encrypt the payload
    rawPayload = container.encrypt( signedContents, self.nonce )
    # sign the payload and attach it to the object
    self.payload = originSig.sign( rawPayload )
    
  # decrypt a payload and return the contents
  # args:
  #   none
  # return:
  #   a decrypted git bundle or False otherwise
  def unwrap(self):
    # don't process the bundle if it's not meant for us
    # check the key fingerprint against our own
    # if it doesn't match
    # return false
    #TODO: Write this code
    #if self.destination is not config.get('global', 'nodename'):
      #return False;
  #else:
    # grab my private key
    with open( config.get('global', 'keypath') + '/' + self.destination + '.private', 'r' ) as destinationPrivateKey:
      destinationKey = self.deserialize(destinationPrivateKey)
    # grab the origin's public key
    with open( config.get('global', 'keypath') + '/' + self.origin + '.public', 'r' ) as originPublicKey:
      originKey = self.deserialize(originPublicKey)
    # grab the origin's verification keyhg
    with open( config.get('global', 'keypath') + '/' + self.origin + '.sighex', 'r' ) as originSigHex:
      originSigKey = self.deserialize(originSigHex)
      originVerify = nacl.signing.VerifyKey(originSigKey, encoder=nacl.encoding.HexEncoder)
    # create a box to decrypt this sucker
    container = Box(destinationKey, originKey)
    # verify the signature
    rawResult = originVerify.verify(self.payload)
    # decrypt it
    rawResult = container.decrypt(rawResult)
    # verify the signature again
    result = originVerify.verify(rawResult)
    
    return result
            
  # grab a git bundle from a repo and create a payload
  # args: 
  #   destination: the public key of the delivery target for the payload
  # returns: 
  #   a payload for delivery
  def pack(self, destination):
    # set the bundle name and output target upfront
    bundleName = self.origin + '.bundle'
    outputTarget = '/tmp/'
    # set the destination
    self.destination = destination
    # change to the git repo's directory
    repo = git.Repo(config.get('global', 'repopath'))
    # if there is no $NODE-current branch, create $NODE-current wherever HEAD is
    repo.git.checkout(B=self.origin)
    # merge master into it
    repo.git.merge('master')
    # create a git bundle from master
    repo.git.bundle('create', outputTarget + bundleName, self.origin)
    # encrypt the bundle using the destination's public key (call serialize() )
    with open(outputTarget + bundleName, 'r') as payloadInput:
       self.wrap(payloadInput.read())
    # export the entire payload with headers into a file
    with open(outputTarget + bundleName + '.endrun', 'w') as payloadFile:
      pickle.dump(self, payloadFile)
    # clean up after ourselves (delete the .bundle file)
    os.remove(outputTarget + bundleName)
  
  # import a payload, decrypt the git payload inside, and perform a git pull
  def unpack(self):
    # set a bunch of variables up front
    repo = git.Repo(config.get('global', 'repopath'))
    bundlePath = config.get('global', 'bundlepath')
    trackingBranch = self.origin + '-remote/' + self.origin
    bundleName = self.origin + '.bundle'
    inputPath = '/tmp/'

    # decrypt the bundle as a bytestream 
    payload = bytes(self.unwrap())
    
    if payload is False:
      print "Bundle is not for this node. Aborting."
      return False

    # save the bundle file in /tmp/
    with open(inputPath +  bundleName, 'wb') as bundleFile:
      bundleFile.write(payload)
    # run a verify against the bundle
    try:
      assert( repo.git.bundle('verify', bundlePath + '/' + bundleName) )
    except: 
      print "Git bundle is not valid."
      return False      
    # copy the bundle file to the destination specified in our .git/config file
    shutil.copyfile(inputPath + bundleName, bundlePath + '/' + bundleName)
    # do a git pull from the bundle file
    repo.git.checkout(self.origin + '-remote/' + self.origin)
    remote = repo.remote(self.origin + '-remote')
    remote.pull(self.origin)
    # checkout master and merge it in
    repo.git.checkout('master')
    repo.git.merge(self.origin + '-remote/' + self.origin)
    # do some clean up
    repo.git.gc()
    # then merge the contents back into the bundle's branch
    repo.git.checkout(self.origin + '-remote/' + self.origin)
    repo.git.merge('master')
    repo.git.checkout('master')
    # clean up after ourselves (delete the encrypted payload and the tarball)
    os.remove('/tmp/' + bundleName)
    
  # issues a receipt entry
  def issueReceipt(self, recepientPubKey):
    # get the current datetime
    timestamp = datetime.datetime.now()
    # perform a SHA256 hash of the encrypted payload
    payload_hash = hashlib.sha256(self)
    # generate a SHA256 hash of the pubkey
    key_hash = hashlib.sha256(recipientPubKey)
    # format a dictionary consisting of the datetime, the recipient's pubkey, and the hash
    json_receipt = { 'node_id': key_hash.hexdigest(), 'timestamp': timestamp, 'fingerprint': payload_hash.hex_digest()  }
    # return the json array to whomever has requested it
    return json.dumps(json_receipt)
  
  # record a receipt on the chain of custody
  # arguments
  #   receiptJson - a JSON object containing receipt data
  def recordChainReceipt(self, receiptJson):
    tempchain = json.loads(self.custodychain)
    tempchain.append(json.loads(receiptJson))
    self.custodychain = tempchain
    
  # a function for queueing a node for delivery
  # arguments
  #   destination: target destination
  def queue(self, destination):
    #TODO: figure out what this needs to do
    pass
    
    
'''
---------------
Helper Functions
---------------
'''  

'''
crypto initialization and checks
'''
def keyCheck(node):
  # check for a valid key pair and return true if found, false otherwise    
  result = False
  if os.path.exists(config.get('global', 'keypath') + '/' + node + '.public') and os.path.exists(config.get('global', 'keypath') + '/' + node + '.private') and os.path.exists(node + '.sig') and os.path.exists(node + '.sighex'):
    result = True
  return result
  
def keyMake(node, path):
  ## create a public, private, and signature key set
  # generate the encryption keypair
  key = PrivateKey.generate()
  # generate the signature key
  sig = nacl.signing.SigningKey.generate()
  verify = sig.verify_key
  sig_hex = verify.encode(encoder=nacl.encoding.HexEncoder)
  
  # write all of the keys to file
  with open(path + '/' + node + '.sig', 'w+') as signing_key:
    pickle.dump(sig, signing_key) 
  with open(path + '/' + node + '.sighex', 'w+') as verify_hex:
    pickle.dump(sig_hex, verify_hex)
  with open(path + '/' + node + '.private', 'w+') as private:
    pickle.dump(key, private)
  with open(path + '/' + node + '.public', 'w+') as public:
    pickle.dump(key.public_key, public)

'''
Node setup and configuration
'''
# generate the keys we need for each node
def generateKeys(nodeTotal, path, prefix = 'node'):
  nodes = []
  keyPath = path + "/keys"
  
  # if the directory doesn't exist, create it
  if not os.path.exists(keyPath):
    os.makedirs(keyPath)
  # switch to that directory
  os.chdir(keyPath)
  print 'Generating keys: ',
  # create one key set for each node
  for node in range (1, nodeTotal + 1):
    nodeName = prefix + str(node)
    keyMake(nodeName, keyPath)
    print("."),
  
  # print a progress message for the user
  print "\nKey generation complete."

# generate an empty repo with the correct number of branches for each node
def repoInit(nodeTotal, path, prefix = 'node'):
  # set up the actual deployment path
  deployPath = path + '/repo'
  
  # create the directory if it's not there yet
  if not os.path.exists(deployPath):
    os.makedirs(deployPath)
  
  print "Creating repo and branches: ",
  # init an empty repo
  repo = git.Repo.init(deployPath)
  
  # write a file so that we have something to move around
  filetext = "This is created during node configuration. Add any additional instructions here."
  readmeName = deployPath + '/README.md'
  with open(readmeName, 'w+') as readme:
    readme.write(filetext)

  # commit said file  
  repo.git.add(readmeName)
  repo.git.commit(m='initial commit to repo')
  
  # create a branch for each node we need to work with
  for node in range(1, nodeTotal + 1):
    nodeName = prefix +  str(node)
    repo.git.checkout(b=nodeName)
    print '.',
  # checkout the master branch again
  repo.git.checkout('master')

  # print a progress message for the user
  print "\nMaster repo creation complete."

# create the node-specific config directories and run the "round robin"
def nodeInit(nodeTotal, path, prefix = "node"):
  
  print "Creating node deployment files: ",
  # define the parent repo
  parentRepo = path + '/repo'
  # define the parent key directory
  parentKeys = path + '/keys'
  # define the parent bundle path
  parentBundles = path + '/bundles'
  if not os.path.exists(parentBundles):
    os.makedirs(parentBundles)

  # set up the deploy directory and set up everything except bundles
  for node in range(1, nodeTotal + 1):
    # define some variables we'll need
    nodeName = prefix + str(node)
    nodePath = path + '/' + nodeName + '-deploy'
    repoPath = nodePath + '/repo'
    keyPath = nodePath + '/keys'
    bundlePath = nodePath + '/bundles'
    # create a directory named nodeX-deploy for each node
    if not os.path.exists(nodePath):
      os.makedirs(nodePath)
    # create a directory called repo
    if not os.path.exists(repoPath):
      os.makedirs(repoPath)    
    # clone the repo in that directory
    repo = git.Repo.clone_from(parentRepo, repoPath)
    # create a bundle of this repo and drop it in the parent folder
    repo.git.checkout(b=nodeName)
    repo.git.bundle('create', parentBundles + '/' + nodeName + ".bundle", nodeName)
    repo.create_tag('bundle-' + nodeName + '-0')
    # create a directory called bundles (leave it empty for now)
    if not os.path.exists(bundlePath):
      os.makedirs(bundlePath)
    # create a directory called keys
    if not os.path.exists(keyPath):
      os.makedirs(keyPath)
    # copy in:
    #  this node's private crypto key
    shutil.copy(parentKeys + '/' + nodeName + '.private', keyPath)
    #  this node's private sig key
    shutil.copy(parentKeys + '/' + nodeName + '.sig', keyPath)
    for files in os.listdir(parentKeys):
      #  everyone's public crypto key
      if files.endswith(".public"):
        shutil.copy(parentKeys + '/' + files, keyPath)
      #  everyone's public sig key
      if files.endswith(".sighex"):
        shutil.copy(parentKeys + '/' + files, keyPath)
    print '.',
  print "\nRepos cloned, keys copied, and bundles created."

  # now create the bundles and set them up in each repo 
  print "Adding bundles as remote repos and creating tracking branches: ",
  for node in range(1, nodeTotal + 1):
    # define some variables we'll need ..
    nodeName = prefix + str(node)
    nodePath = path + '/' + nodeName + '-deploy'
    repoPath = nodePath + '/repo'
    bundlePath = nodePath + '/bundles'  
    repo = git.Repo(repoPath)
    # copy every bundle except yourself
    for files in os.listdir(parentBundles):
      if not files.startswith(nodeName):
        shutil.copy(parentBundles + '/' + files, bundlePath)
    # add a remote for every bundle you have
    for files in os.listdir(bundlePath):
      remoteName = files.split('.')
      remote = repo.create_remote(remoteName[0] + '-remote', bundlePath + '/' + files)
      remote.fetch()
      trackingBranch = remoteName[0] + '-remote/' + remoteName[0]
      repo.git.checkout(b=trackingBranch)
    repo.git.checkout('master')
    print '.',
  print "\nProcess complete."
    
  print str(nodeTotal) + " nodes ready for deployment."

'''
Payload functions
'''

# receive a payload
def receive(payload):
  with open(payload, 'r') as payloadFile:
    try:
      raw_payload = pickle.load(payloadFile) 
      raw_payload.unpack()
      #TODO: catch payloads that don't belong to us and shunt them into the queue
    except:
      print "The payload is invalid. Please check the file's validity."
      return False

# transmit a payload
def transmit(destination):
  try:
    payload = Payload()
    payload.pack(destination)
  except:
    print "Error with creating payload. Please check repo integrity."
    return False

'''
Chain of custody functions
'''
def chainRecord(payload):  
  #record the chain of custody info here
  with open(payload, 'r') as payloadFile:
    try:
      with open( config.get('global', 'keypath') + '/' + config.get('global', 'nodename') + '.public', 'r' ) as keyFile:
        pubKey = pickle.load(keyFile)
        raw_payload = pickle.load(payloadFile)
        raw_payload.issue_receipt(self, pubKey)
        # add sqlite code here
    except:
      print "Invalid payload. Cannot record receipt."
      return False
  pass

#logging functions
#TODO: all of this

def dbConnect(dbName):
  conn = sqlite3.connect(dbName)
  return conn.cursor()

# initialize our DBs
def initDB( c = dbConnect(':memory:') ):
  c.execute('''CREATE TABLE receipts (date text, nodeID text, payloadHash text)''')
  c.execute('''CREATE TABLE map (date text, nodeID text)''')

def mapRecord(mapdata):
  c = dbConnect(':memory:')
  c.   
  
  pass
  
def receiptRecord(receipt):
  # validate inputs
  inputs = (receipt[0],)
  # connect to db
  conn = sqlite3.connect(':memory:')
  c = conn.cursor()
  
  # insert data into record db
  
  
  
  pass

# clear out the DBs
def flushDB():
  conn = sqlite3.connect(':memory:')
  c = conn.cursor()
  # drop and recreate the tables
  
  pass
