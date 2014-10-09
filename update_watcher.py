"""
Robert Powell
Sometime during the summer

Watch a set of websites for changes in content. Works by downloading a baseline of the site
then sending an email notification if any changes to the content happen after that. Once
a change has been registered, it is remembered so you won't get updates on things like photo banners
and such. Will initially give lots of false positives if sites contain dynamic materials

launch by 'python ./update_watcher.py'
"""

import threading
import urllib
import urllib2
import lxml.html
import socket
import smtplib

class Notifier(object):
    """Class to handle sending notifications about updates"""

    def __init__(self, email_list, creds):

        self.email_list = email_list
        self.server = smtplib.SMTP('smtp.gmail.com:587')
        self.creds = creds

    def send_email(self, raw_updates):
        """Take a list of updates and send them in an email"""

        self.prep_server()
        message = self.prep_message(raw_updates)

        try:
            self.server.sendmail(message[0], message[1], message[2])
            print "Successfully sent email"
        except smtplib.SMTPException:
            print "Error: unable to send email"

    def prep_server(self):
        """Make connection to mail server before sending mail"""

        self.server.ehlo()
        self.server.starttls()
        self.server.login(self.creds[0], self.creds[1])

    def prep_message(self, raw_updates):
        """Get the message itself ready for sending"""

        sender = 'rpowell@bangordailynews.com'
        receiver = 'rpowell@bangordailynews.com'
        message = "From %s\r\n" % sender
        message += "To: %s\r\n" % receiver
        message += "Subject: Updated Election Sites \n"

        updates = self.prep_updates(raw_updates)
        for update in updates:
            message += update
        return (sender, receiver, message)

    def prep_updates(self, updates):
        """Clean the list of given updates for pretty email"""

        pretty_updates = []
        for site in updates:
            pretty_updates.append(site[0] + '\n')
            for new_link in site[2]:
                if 'http' not in new_link:
                    pretty_updates.append('-' + site[1] + new_link + '\n')
                else:
                    pretty_updates.append('-' + new_link + '\n')
        return pretty_updates


class Downloader(threading.Thread):
    """Class for creating threads to download pages in parallel"""

    def __init__(self, url):

        self.url = url
        self.result = None
        self.done = False
        self.headers = {'cache-control':'no-cache', 'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:10.0) Gecko/20100101 Firefox/10.0'}
        threading.Thread.__init__(self)

    def get_result(self):
        """Return the last downloaded page"""

        return self.result

    def run(self):
        """Built in method that gets executed on thread.start()"""

        try:
            req = urllib2.Request(self.url, None, self.headers)
            response = urllib2.urlopen(req, timeout=5)
            self.result = response
            self.done = True
        except socket.timeout:
            print '\n\n', self.url, 'has timed out.'
            self.done = True
        except Exception, error:
            print '\n\n', self.url, error
            self.done = True


class Source(object):
    """Abstraction to contain different sources of url lists"""

    def __init__(self, name, path, is_online=False):

        self.name = name
        self.path = path
        self.is_online = is_online
        self.records = []

    def load_file(self):
        """Load the contents of the source file for reading"""
        if self.is_online:
            self.load_from_web()
        else:
            self.load_from_disk()

    def load_from_disk(self, alt_path=False):
        """Load specifically from a local file"""

        working_path = self.path
        if alt_path:
            working_path = self.name
        with open(working_path, 'r') as source:
            for line in source:
                line = line.split(',')
                self.records.append((line[0], line[1]))

    def load_from_web(self):
        """Download a csv file from internet to local file"""

        urllib.urlretrieve(self.path, self.name)
        self.load_from_disk(True)

    def return_records(self):
        """Public method for returning the record dictionary"""

        return self.records


class Site(object):
    """Abstraction for the websites themselves"""

    def __init__(self, descriptor, url):

        self.desc = descriptor
        self.url = url
        self.body = ''
        self.links = []
        self.downloader = Downloader(self.url)
        self.last_update = None
        self.has_updates = False

    def rebuild_downloader(self):
        """Initialze a new thread to download html source"""

        self.downloader = Downloader(self.url)

    def get_body(self):
        """Download the html source for the site"""

        self.downloader.start()

    def get_body_links(self):
        """Get the links from the last downloaded body"""

        new_body = self.downloader.get_result()
        if new_body != None:
            dom = lxml.html.parse(new_body)
            dom_links = dom.xpath('//a/@href')
            return dom_links
        else:
            return []

    def update_body(self):
        """Set the object body to the current online body"""

        self.body = self.downloader.get_result()

    def update_body_links(self):
        """Set the current links to the last returned set of links"""

        self.links = self.get_body_links()

    def compare_body_links(self):
        """Check for changes in the number of links on page"""

        changes = []
        dom_links = self.get_body_links()
        for link in dom_links:
            if link not in self.links:
                changes.append(link)
        return changes

    def compare_body(self):
        """Check for changes in html source as a whole"""
        new_body = self.downloader.get_result()
        if new_body != self.body:
            return True
        else:
            return False

    def check_for_update_link(self):
        """Check the site for changes by the links method"""

        possible_changes = self.compare_body_links()
        if len(possible_changes) > 0:
            self.last_update = possible_changes
            self.links += possible_changes
            self.body = self.update_body()
            self.has_updates = True

    def check_for_update_body(self):
        """Check the site for changes by the body method"""

        has_changed = self.compare_body()
        if has_changed:
            self.has_updates = True
            self.body = self.update_body()


    def get_updates(self):
        """Grab the latest updates for a page and clear the flag"""

        self.has_updates = False
        return self.last_update


class Monitor(object):
    """Monitor object to handle watching websites from a source"""

    def __init__(self, source):
        self.sites = []
        self.proc = []
        self.source = source

    def process_sites(self):
        """Queue sites to download new html content"""

        unprocessed = []
        for site in self.sites:
            unprocessed.append(site)

        while len(unprocessed) != 0 or len(self.proc) != 0:
            print_string = "%s currently processing. %s currently waiting. \r"
            print print_string % (len(self.proc), len(unprocessed)),

            if len(self.proc) < 25 and len(unprocessed) != 0:
                thread = unprocessed.pop()
                thread.get_body()
                self.proc.append(thread)

            self.proc = [t for t in self.proc if not t.downloader.done]

        print "Finished downloading websites!                    "

    def build_sites(self):
        """Build the site objects based on data from source"""

        current_records = self.source.return_records()
        for record in current_records:
            if record[1] != '' and record[1][0:4] == 'http':
                self.sites.append(Site(record[0], record[1]))
        self.process_sites()
        for site in self.sites:
            site.update_body_links()
            site.rebuild_downloader()

        print "Strapping Sites to Minimize update emails"
        for _ in range(20):
            self.check_updates()

    def check_updates(self):
        """Gather updated sites and get changes"""

        self.process_sites()
        updated = []
        for site in self.sites:
            site.check_for_update_link()
            if site.has_updates:
                updated.append((site.desc, site.url, site.get_updates()))
            site.rebuild_downloader()
        return updated


#If you want to make it command line accessible look at the argparse module

#Global time to watch on downloading sites, probably in seconds
TIMEOUT = 10
socket.timeout(TIMEOUT)

#Set the source to be the online google docs file -- it will redownload it periodically if I remember correctly
S = Source('BDN', 'https://docs.google.com/spreadsheet/pub?key=0AuY6j4GH8THydHA2bXN4ZXJXSGhic1JTbW1MZTBrREE&single=true&gid=4&output=csv', is_online=True)
S.load_file()
M = Monitor(S)
#Get the first state of the websites, any changes after the initial load will be regarded as 'updates'
M.build_sites()
while True:
    print M.check_updates()

