# -*- coding:utf-8 -*-
import urllib
import urllib2
import re
import os
import urlparse
import sys,traceback
import sqlite3
import plistlib
import logging  
import logging.handlers  

handler = logging.StreamHandler(sys.stdout)
fmt = '%(asctime)s |%(filename)s:%(lineno)s |%(name)s :%(message)s'  
  
formatter = logging.Formatter(fmt)
handler.setFormatter(formatter)
  
logger = logging.getLogger('Tester')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG) 

class SpiderPartsAlpha:
    #this spider is created for 1.8.0_xx javadoc set, I beleive they should be same so far
    ClassesListPage = 'allclasses-noframe.html'
    PackageSummaryPage = 'overview-summary.html'
    PackageRefRe = re.compile('<td class="colFirst"><a href="(.*?)">(.*?)</a></td>')
    ClassesRefRe = re.compile('<li><a href="(.*)".*?title="(.*?) in .*?"')
    CsRefRe = re.compile('href="(\..*?\.css)"')
    MemberRefRe = re.compile('<span class="memberNameLink"><a href="(.*?html#.*?)">(.*?)</a></span>')
    SubClassRe = re.compile('<span class="memberNameLink"><a href="(.*?)" title="(.*?) in')
    SummaryRe = re.compile('<div class="summary">(.*?)<div class="details">', re.S)
    MemberSummaryRe = re.compile('<a name="(.*?)">(.*?)</ul>', re.S)

class SpiderPartsBeta(SpiderPartsAlpha):
    #this spider is created for 1.6.0_xx javadoc set, I beleive they should be same so far
    PackageRefRe = re.compile('<A HREF="(.*?\.html)">([^ <]*?)</A>')
    ClassesRefRe = re.compile('<A HREF="(.*)".*?title="([^ "].*?) in .*?"')
    SummaryRe = re.compile('(<!-- ========[^=]*?SUMMARY.*?)DETAIL', re.S)
    MemberSummaryRe = re.compile('<!-- ========(.*?SUMMARY)(.*?)</TABLE>', re.S)
    SubClassRe = ClassesRefRe
    #<A HREF="../../org/bson/BasicBSONCallback.html#_put(java.lang.String, java.lang.Object)">_put</A>
    MemberRefRe = re.compile('<A HREF="([^:]*?)">([^ <"]*?)</A>')

class SpiderParts:
    VersionMap = {
            "1.8.0" :SpiderPartsAlpha,
            "1.6.0" :SpiderPartsBeta
            }
    versionReg = re.compile('<!-- Generated by javadoc \((.*?)\)')

    @staticmethod
    def getSpider(root):
        #find the doc version
        try:
            request = urllib2.Request(root )
            response = urllib2.urlopen(request)
            msg = response.read()
            versionMatch = SpiderParts.versionReg.findall(msg)
            for version in versionMatch:
                logger.debug("The doc version is " + version)
                for key, value in SpiderParts.VersionMap.items():
                  if version.find(key) != -1:
                      logger.debug("match spider found")
                      return value
            logger.debug(msg)
            return None
        except urllib2.URLError, e:
            if hasattr(e,"code"):
                logger.error(e.code)
            if hasattr(e,"reason"):
                logger.error(e.reason)
            return None
    

class IndexDataBase:
    def __init__(self, docSetName):
        self.connection = sqlite3.connect('./%s.docset/Contents/Resources/docSet.dsidx' % docSetName)
        self.course = self.connection.cursor()
        self.course.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
        self.course.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')
        self.insertStr = '''INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?);'''

    def __del__(self):
        self.connection.commit()
        self.connection.close()

    def commit(self):
        self.connection.commit()

    def insert(self, name, type, path):
        self.course.execute(self.insertStr, (name, type, path))

#This is the base Spider, you should only use this spider
class Spider:
      ##const parameters
    dirPathRe = re.compile('(.*)/')
    docSetNameReg = re.compile('(.*)\.html*')
    rootUrlReg = re.compile('(.*/).*?\.html*')

    def __init__(self,root, docSetName):
        self.createPath('./%s.docset/Contents/Resources/Documents/test.txt' % docSetName)
        self.rootUrl = root
        for docRoot in Spider.rootUrlReg.findall(root):
            # if the root is with html, should remove the html tail
            self.rootUrl = docRoot
        logger.debug("root url is:" + self.rootUrl)
        self.parts = SpiderParts.getSpider(root)
#don't sure about index page, are they the same?
        self.searchedUrl = set()
        self.docSetName = docSetName
        self.initPlist()
        self.tagDic = {
            'annotation':'Annotation',
            'nested.class':'Class',
            'class':'Class',
            'interface':'Interface',
            'enum':'Enum',
            'enum.constant':'Enum',
            'method':'Method',
            'constructor':'Constructor',
            'field':'Constant'
           }
        self.db = IndexDataBase(docSetName)
    
    def pullWeb(self, url):
        try:
            if url in self.searchedUrl:
              return ""
#            request = urllib2.Request(url,headers = self.headers)
            request = urllib2.Request(url,)
            response = urllib2.urlopen(request)
            rspMsg = response.read()
            self.searchedUrl.add(url)
            return rspMsg
        except urllib2.URLError, e:
            if hasattr(e,"code"):
                logger.error(e.code)
            if hasattr(e,"reason"):
                logger.error(e.reason)
            logger.error("request:%s" % url)
            return ""

    def pullSummaryPage(self):
        summaryPage = urlparse.urljoin(self.rootUrl , self.parts.PackageSummaryPage)
        logger.debug("the summary page is:" + summaryPage)
        summaryPageMsg = self.pullWeb(summaryPage)
        self.write2File(summaryPageMsg, summaryPage)
        packageRe = self.parts.PackageRefRe
        allPackages = packageRe.findall(summaryPageMsg)
        for package in allPackages:
            packageRequest = urlparse.urljoin(summaryPage, package[0])
            packageMsg = self.pullWeb(packageRequest)
            if "" == packageMsg:
                continue
            packagePath = self.write2File(packageMsg, packageRequest)
            name = self.getClassName(packagePath)
            self.db.insert(name[0], "Package", packagePath)
  


    def initPlist(self):
        plistInfo = {
            "CFBundleIdentifier": "javadoc",
            "CFBundleName" : self.docSetName,
            "DocSetPlatformFamily": "javadoc",
            "dashIndexFilePath" : self.parts.PackageSummaryPage,
            "DashDocSetFamily" :"java",
            "isDashDocset": "YES"
            }
        fileName = './%s.docset/Contents/Info.plist' %self.docSetName
        self.createPath(fileName)
        plistlib.writePlist(plistInfo, fileName)


    def createPath(self,file):
      docPath = Spider.dirPathRe.findall(file)
      for p in docPath:
          if os.path.exists(p) is not True :
              os.makedirs(p)
          return p
      return ""

    def write2File(self, msg, url):
        fileName = url.replace(self.rootUrl, "./%s.docset/Contents/Resources/Documents/" % self.docSetName)
        logger.debug("now save %s to %s" % (url, fileName) )
        path = self.createPath(fileName)
        fileHandler = open(fileName,'w')
        fileHandler.write(msg)
        fileHandler.close()
        return fileName.replace("./%s.docset/Contents/Resources/Documents/" % self.docSetName,"")

    def getClassName(self, url):
        allClass = Spider.docSetNameReg.findall(url)
        for path in allClass:
            splited = path.split('/')
            return ".".join(splited), splited[-1]
        return "", ""

    def analyzeClassMsg(self, url, type):
        classMsg = self.pullWeb(url)
        if "" == classMsg:
            return
        #save classes
        fileName = self.write2File(classMsg, url)
        classNameA, classNameB = self.getClassName(fileName)
    
        typeName = self.getTypeName(type)
        self.db.insert(classNameA, typeName, fileName)
        self.db.insert(classNameB, typeName, fileName)
    
        #find all method in this file and insert into the db
        methodSummaryStr = self.parts.SummaryRe.findall(classMsg)
        for str in methodSummaryStr:
            methodSummary = self.parts.MemberSummaryRe.findall(str)
            for method in methodSummary:
                #find field summary at first
                if -1 == method[0].lower().find("summary"):
                  # if no summary is found, than this could be something like "method.inherited from xxx", so we just continue it
                    continue
                memberFields = self.parts.MemberRefRe.findall(method[1])
                fieldType = self.getTypeName(method[0].replace(".summary",""))
                if 'Class' == fieldType:
                    SubClasses = self.parts.SubClassRe.findall(method[1])
                    for subClass in SubClasses:
                        logger.debug("find subClass:%s,%s" % subClass)
                        methodUrl = urlparse.urljoin(url, subClass[0])
                        self.analyzeClassMsg(methodUrl, subClass[1])
                else:
                    for field in memberFields:
                        logger.debug("find method(%s, %s)" % field)
                        methodIndex = urlparse.urljoin(fileName, field[0])
                        self.db.insert(field[1], fieldType, methodIndex)
              
            csFile = self.parts.CsRefRe.findall(classMsg)
            for files in csFile:
                downloadPath = urlparse.urljoin(url,  files)
                cssFile = self.pullWeb(downloadPath)
                if cssFile != "":
                    self.write2File(cssFile, downloadPath)

    def getTypeName(self, javaTag):
        if javaTag.lower() in self.tagDic:
            return self.tagDic[javaTag]
        else:
            #check mapping
            for key in self.tagDic:
                if -1 != javaTag.lower().find(key):
                    return self.tagDic[key]
            logger.error("unexpected tag:%s"%javaTag)
            return ""
    
    def run(self):
        try:
            allClassUrl = urlparse.urljoin(self.rootUrl , self.parts.ClassesListPage)
            rspMsg = self.pullWeb(allClassUrl)
            # also save method list
            self.write2File(rspMsg, allClassUrl)
    
            # I don't care if this is a doc or not, just get the first one, if nothing exist, panic will rasie    
            #find the classes and interfaces, also find the href
            self.pullSummaryPage()
            allClass = self.parts.ClassesRefRe.findall(rspMsg)
            for cur in allClass:
              self.db.commit()
              requestUrl = urlparse.urljoin(self.rootUrl , cur[0])
              self.analyzeClassMsg(requestUrl, cur[1])
        except:
            tb = traceback.format_exc()
            logger.error(tb)

