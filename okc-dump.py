# okc-dump.py : an OkCupid question backup utility
# Copyright 2013 Kevin Rauwolf
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import sys
import urllib
import urllib2
import cookielib
import ConfigParser
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

kLoginUrl = "https://www.okcupid.com/login"
kQuestionUrl = "http://www.okcupid.com/profile/{}/questions"
kMessageUrl = "http://www.okcupid.com/messages"
kQtextFinder = re.compile(r"^qtext_(\d+)")
kQuestionFinder = re.compile(r"^question_(\d+)")
kThreadFinder = re.compile(r"threadid=(\d+)")
kMessageFinder = re.compile(r"^message_(\d+)")
kTimestampFinder = re.compile(r"(\d+), 'MESSAGE_FORMAT'")
kQuestionsPerPage = 10
kThreadsPerPage = 30
kConfigFile = "okc-dump.ini"

class Answer(object):
	def __init__(self, text, mine, match):
		self.text = text
		self.mine = mine
		self.match = match

class Question(object):
	def __init__(self, qid, text, public, importance, answers, explanation):
		self.qid = qid
		self.text = text
		self.public = public
		self.importance = importance
		self.answers = answers
		self.explanation = explanation

class Message(object):
	def __init__(self, mid, tid, sender, recipient, timestamp, text):
		self.mid = mid
		self.tid = tid
		self.sender = sender
		self.recipient = recipient
		self.timestamp = timestamp
		self.text = text

def message_type_to_folder(is_sent):
	return 2 if is_sent else 1

def parse_questions(page):
	soup = BeautifulSoup(page)
	questions = list()
	for question in soup.find_all(id=kQuestionFinder):
		prompt = question.find(id=kQtextFinder)
		if not prompt:
			continue
		qid = kQtextFinder.match(prompt["id"]).group(1)
		question_text = prompt.string
		answer_div = prompt.find_next_sibling()
		answers = list()
		for response in answer_div.find_all("li"):
			answer = response.string
			classes = response["class"]
			mine = "mine" in classes
			match = "match" in classes
			answers.append(Answer(answer, mine, match))
		explanation = None
		textarea = answer_div.find("textarea")
		if textarea.contents:
			explanation = textarea.string
		importance_input = question.find(id="question_{}_importance".format(qid))
		importance = importance_input["value"]
		public_input = question.find(id="public_{}".format(qid))
		public = public_input["value"] == "on"
		questions.append(Question(qid, question_text, public, importance, answers, explanation))
	return questions

def parse_threads(page):
	soup = BeautifulSoup(page)
	threads = list()
	for entry in soup.find_all(href=kThreadFinder):
		matches = kThreadFinder.search(entry["href"])
		threads.append(matches.group(1))
	return threads

def parse_thread(page, thread_id, username):
	soup = BeautifulSoup(page)
	messages = list()
	buddy_name = soup.find(attrs={ "name": "buddyname"})['value']
	for message in soup.find_all(id=kMessageFinder):
		mid = kMessageFinder.match(message["id"]).group(1)
		if "from_me" in message["class"]:
			sender = username
			recipient = buddy_name
		else:
			sender = buddy_name
			recipient = username
		timestamp = None
		for script in message.find_all("script"):
			if script.contents:
				matches = kTimestampFinder.search(script.string)
				if matches:
					timestamp = matches.group(1)
		body = message.find(class_="message_body")
		text = "\n".join([t for t in body.stripped_strings])
		messages.append(Message(mid, thread_id, sender, recipient, timestamp, text))
	return messages

def login(cj, opener, username, password):
	login_data = urllib.urlencode({
		"username": username,
		"password": password,
	})
	response = opener.open(kLoginUrl, login_data)
	return response.read()

def get_question_count(cj, opener, username):
	response = opener.open(kQuestionUrl.format(username))
	soup = BeautifulSoup(response.read())
	count = soup.find(id="q_num_total")
	return int(count.string)

def get_question_page(cj, opener, username, low):
	response = opener.open(kQuestionUrl.format(username) + "?low={}".format(low))
	questions = parse_questions(response.read())
	return questions

def get_thread_count(cj, opener, username, is_sent):
	response = opener.open(kMessageUrl + "?folder={}".format(message_type_to_folder(is_sent)))
	soup = BeautifulSoup(response.read())
	count = soup.find(class_="last")
	return int(count.string) * kThreadsPerPage

def get_thread_page(cj, opener, username, low, is_sent):
	response = opener.open(kMessageUrl + "?low={}&folder={}".format(low, message_type_to_folder(is_sent)))
	threads = parse_threads(response.read())
	return threads

def get_thread(cj, opener, username, thread_id):
	response = opener.open(kMessageUrl + "?readmsg=true&threadid={}".format(thread_id))
	messages = parse_thread(response.read(), thread_id, username)
	return messages

def to_xml(questions, messages):
	root = ET.Element("okc-backup")
	questions_tag = ET.SubElement(root, "questions")
	for question in questions:
		attributes = {
			"id": question.qid,
			"importance": question.importance,
		}
		if question.public:
			attributes["public"] = "true"
		question_tag = ET.SubElement(questions_tag, "question", attributes)
		prompt_tag = ET.SubElement(question_tag, "prompt")
		prompt_tag.text = question.text
		responses_tag = ET.SubElement(question_tag, "responses")
		for answer in question.answers:
			attributes = dict()
			if answer.mine:
				attributes["mine"] = "true"
			if answer.match:
				attributes["match"] = "true"
			response_tag = ET.SubElement(responses_tag, "response", attributes)
			response_tag.text = answer.text
		if question.explanation:
			explanation_tag = ET.SubElement(question_tag, "explanation")
			explanation_tag.text = question.explanation
	messages_tag = ET.SubElement(root, "messages")
	for message in messages:
		attributes = {
				"id": str(message.mid),
				"thread_id": str(message.tid),
				"timestamp": str(message.timestamp),
				"sender": message.sender,
				"recipient": message.recipient,
		}
		message_tag = ET.SubElement(messages_tag, "message", attributes)
		message_tag.text = message.text
	return ET.ElementTree(root)

if __name__ == "__main__":
	config = ConfigParser.SafeConfigParser()
	config.read(kConfigFile)
	cj = cookielib.CookieJar()
	opener = urllib2.build_opener(urllib2.HTTPRedirectHandler(), urllib2.HTTPHandler(), urllib2.HTTPSHandler(), urllib2.HTTPCookieProcessor(cj))
	username = config.get("login", "username")
	login(cj, opener, username, config.get("login", "password"))
	# Questions
	questions = list()
	messages = list()
	# TODO parameterize
	if False:
		question_count = get_question_count(cj, opener, username)
		sys.stderr.write("Fetching {} questions\n".format(question_count))
		sys.stderr.flush()
		for low in range(1, question_count, kQuestionsPerPage):
			questions.extend(get_question_page(cj, opener, username, low))
			sys.stderr.write(".")
			sys.stderr.flush()
		sys.stderr.write("\n")
	# Messages
	# TODO parameterize
	if True:
		threads = set()
		# Sent
		thread_count = get_thread_count(cj, opener, username, True)
		sys.stderr.write("Found {} sent message threads\n".format(thread_count))
		sys.stderr.flush()
		for low in range(1, thread_count, kThreadsPerPage):
			threads.update(get_thread_page(cj, opener, username, low, True))
			sys.stderr.write(".")
			sys.stderr.flush()
		sys.stderr.write("\n")
		# Received
		thread_count = get_thread_count(cj, opener, username, False)
		sys.stderr.write("Found {} received message threads\n".format(thread_count))
		sys.stderr.flush()
		for low in range(1, thread_count, kThreadsPerPage):
			threads.update(get_thread_page(cj, opener, username, low, False))
			sys.stderr.write(".")
			sys.stderr.flush()
		sys.stderr.write("\n")
		sys.stderr.write("Fetching threads\n")
		sys.stderr.flush()
		for thread in threads:
			messages.extend(get_thread(cj, opener, username, thread))
			sys.stderr.write(".")
			sys.stderr.flush()

	xml = to_xml(questions, messages)
	xml.write(sys.stdout, encoding="UTF-8")
