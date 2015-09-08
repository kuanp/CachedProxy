# using python 2.7.9
# Module Proxy:
# Testing: use without arguments or enter singular port number. 
import blist
import datetime
import httplib
import json
import random
import time
import threading
import sys
import signal
import urlparse
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn

# some modular variables, mostly for main's testing purposes. 
server_host = 'localhost'
server_port = 8080
PORT_MAX = 65535
CACHE_CONFIG_FILE = 'cache_config.json'
		
class CacheObject:
	""" 
	Fields: 
	url, last access time, expiration time, size, data
	"""
	def __init__(self, _url, _lastAccessTime, _expirationTime, _size, _data):
		self.url = _url
		self.lastAccessTime = _lastAccessTime
		self.expirationTime = _expirationTime
		self.size = _size
		self.data = _data
	
		
class Cache:
	""" 
	This Cache is constructed based several assumptions:
	1. Uses tend to access the same elements more than others
		- In web surfing and data surfing, often same sets of data are 
		visited in a short amount of time over and over again, 
		afterwhich its relevance wanes and other items become more popular. 
		
		Therefore: We can implement this cache be small and active in throwing out older 
		entries even if they haven't expired yet, giving preference to more recently accessed entries. 
		
	2. Resources take a really long time to expire
		- Quickly changing resources require constantly refreshing, 
		which makes caching them less efficient. 
		- Long expiration time likely in data access situations 
		where data tables has already been stored. This data is likely final,
		and changes are rare. 
		- We'll only cache when the cache time is more than a particular minumum.
		
	3. Frequency of access matters more than the size of the requested resource. 
		- Primarily because it is expensive to put big chunks of data in memory, 
		especially if it's only used a few times. 
	
	As such, this Cache will be implemented with a 2 sorted lists and a map.
		The first sorted list (tree-implementation) is a list that will keep track of 
		the most recent look up time of a url. 
		Second sorted list will keep track of the amount of time remaining, "shelf-life" 
		of each cache entry. 
		The map will contain a mapping from the url to the data itself. 
	"""

	def __init__(self, config = CACHE_CONFIG_FILE):
		properties = json.load(open(config))
		self.maxDuration = properties['cacheDuration']
		self.minDuration = properties['cacheMinDuration']
		self.maxBytes = properties['cacheSizeBytes']
		self.maxElems = properties['cacheSizeElements']
		self.numElems = 0
		self.numBytes = 0
		self.lock = threading.Lock()
		
		self.accessList = blist.sortedlist(key=lambda cachedObject: cachedObject.lastAccessTime) # sort by last access time. (url, lastAcessTime)
		self.expireList = blist.sortedlist(key=lambda cachedObject: cachedObject.expirationTime) # sort by time remaining. (url, expire-date)
		self.map = {} # elements will be of the form, {url: CacheObject}
	
	def checkCacheIntegrity(self):
		""" 
		Deletes entries as necessary keep the expirationDates and maxbytes and maxElems happy 
		This method should always take place while the cache is locked for accesss.
		"""
		# print "I dont want to be here"
		while (self.numElems > self.maxElems or self.numBytes > self.maxBytes):
			toRemove = self.accessList.pop(0)
			self.expireList.remove(toRemove)
			del self.map[toRemove.url]
			
			self.numBytes -= toRemove.size
			self.numElems -= 1

		while (self.numElems > 0 and self.expireList[0].expirationTime < time.time()):
			#print "I can't be here"
			toRemove = self.expireList.pop(0)
			self.accessList.remove(toRemove)
			del self.map[toRemove.url]
			
			self.numBytes -= toRemove.size
			self.numElems -= 1
			
	def cache(self, url, data, numBytes, accessTime, duration):
		""" Inserts a new cache entry into the cache, updating all fields as necessary """
		if duration < self.minDuration:
			return
		elif duration > self.maxDuration:
			duration = self.maxDuration
		
		self.lock.acquire()
		
		# Just in case user calls this when there already exists a cache
		if (url in self.map.keys()):
			print "INVALID CACHE USAGE, " + url + " is already cached!"
		else:
			toCache = CacheObject(url, accessTime, accessTime + duration, numBytes, data)
			self.numElems += 1
			self.numBytes += numBytes
			
			self.map[url] = toCache
			self.accessList.add(toCache)
			self.expireList.add(toCache)
			
			self.checkCacheIntegrity()
		self.lock.release()
	
	def get(self, url):
		""" If not found or expired, return None. Else, return the data and modify the last access list"""
		self.lock.acquire()
		self.checkCacheIntegrity()
		result = None
		if (url in self.map.keys()): # O(1) check
			# Get the url, update it with current time in last access, and send back the data
			oldCache = self.map[url]
			timeNow = time.time()
			self.accessList.remove(oldCache)
			oldCache.lastAccessTime = timeNow
			self.accessList.add(oldCache)
			result = oldCache
			
		self.lock.release()
		return result
		
	def has(self, url):
		""" O(1) check to see if url is cached or not """
		self.lock.acquire()
		result = url in self.map.keys()
		self.lock.release()
		return result

class CachedRequestHandler(BaseHTTPRequestHandler):
	""" 
	A RequestHandler object subclassed from BasicHTTPRequestHandler. 
	It only implements the GET requests, every other form of request is 
	simply forwarded onwards without any modification.
	
	Use when constructing a server. 
	"""		
	def do_POST(self):
		""" Do nothing but forwarding info back and forth """
		parsedRequest = urlparse.urlparse(self.path)		

		self.send_response(400, "We don't handle POST")	
	
	def do_GET(self):
		"""Respond to a GET request."""
		parsedRequest = urlparse.urlparse(self.path)		

		
		# Attempt cache check. 
		#self.server.test += 1
		
		#print self.server.test
		
		
		# Attempt to connect requested server.
		# Randomize the port
		# port = random.randint(0, PORT_MAX)
		# print port
		try:
			# print parsedRequest.netloc
			# print parsedRequest.path
			# Sets a connection with a server and relays the user's request, with a 10 second timeout.
			connection = httplib.HTTPConnection(parsedRequest.netloc, timeout = 10)
			connection.request(self.command, parsedRequest.path)
			response = connection.getresponse()
			
			#print response.status
			#print response.read()
			if response.status >= 200 and response.status < 300:
				self.send_response(response.status)
				headers = response.getheaders()
				for header in headers:
					self.send_header(header[0], header[1])
				self.end_headers()
				data = response.read()
				self.wfile.write(data)
				
				# Now Cache this. 
				
			
			elif response.status >= 300 and response.status < 400:
				self.send_response(response.status)
				headers = response.getheaders()
				for header in headers:
					self.send_header(header[0], header[1])
				self.end_headers()
				data = response.read()
				self.wfile.write(data)
			
			else:
				self.send_response(400)
				
			# Done with this connection, so just go ahead and collect the resources
			connection.close()
			
			#self.send_header("Content-type", "text/html")
			#self.end_headers()
			#self.wfile.write(response.read())

		except httplib.NotConnected:
			print "failed to connect"
		except httplib.InvalidURL:
			print "Server not found"
		except httplib.BadStatusLine:
			print "we didn't understand the message sent by the requested server"
		
		# self.wfile.write("<html><head><title>Title goes here.</title></head>")
		# self.wfile.write("<body><p>This is a test.</p>")
		# If someone went to "http://something.somewhere.net/foo/bar/",
		# then s.path equals "/foo/bar/".
		# self.wfile.write("<p>You accessed path: %s</p>" % self.path)
		# self.wfile.write("</body></html>")

class ProxyServer(HTTPServer):
	""" 
	Extends the basic HTTPServer class to initialize caches and mutex/semaphores 
	that may be needed for threading access operations. Handles requests sequentially. 
	
	*server_address could come in the form of tuples, as in (server_host, server_port) 
	Usage: ProxyServer(server_address, RequestHandler)
	"""
	
	def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
		"""Constructor.  May be extended, do not override."""
		HTTPServer.__init__(self, server_address, RequestHandlerClass)
		self.cache = Cache() 

class ThreadedProxyServer(ThreadingMixIn, ProxyServer):
    """
	Python built-in threading server feature to handle requests in separate threads. 
	Primary objective of this project. 
	
	Usage is the same as ProxyServer initialization:
	server = ThreadedProxyServer(server_address, RequestHandler)
	"""
	
	
if __name__ == '__main__':
	if (len(sys.argv) == 2):
		try:
			if (int(sys.argv[1]) > 0 and int(sys.argv[1]) <= 65535):
				server_port = int(sys.argv[1])
			else: 
				print "Port out of range, using default port 8080."
		except ValueError:
			print "Port needs to be a number"
			exit(0)

	print 'Proxy has started and is listening to requests, use <Ctrl-C> to stop'
	
	# Shuts down all concurrent threads that the server spawns.
	ThreadingMixIn.daemon_threads = True
		
	server = ThreadedProxyServer((server_host, server_port), CachedRequestHandler)
	

	try:
		server.serve_forever()
	except KeyboardInterrupt:
		# Add graceful handling of shutting if necessary.
		#server.shutdown()
		print('Shutting down proxy...')

