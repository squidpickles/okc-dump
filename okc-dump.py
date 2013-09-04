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
kQtextFinder = re.compile("^qtext_(\d+)")
kQuestionFinder = re.compile("^question_(\d+)")
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

def parse(page):
	soup = BeautifulSoup(page)
	questions = list()
	for question in soup.find_all(id=kQuestionFinder):
		prompt = question.find(id=kQtextFinder)
		if not prompt:
			continue
		qid = kQtextFinder.match(prompt["id"]).group(1)
		question_text = prompt.contents[0].strip()
		answer_div = prompt.find_next_sibling()
		answers = list()
		for response in answer_div.find_all("li"):
			answer = response.contents[0].strip()
			classes = response["class"]
			mine = "mine" in classes
			match = "match" in classes
			answers.append(Answer(answer, mine, match))
		explanation = None
		textarea = answer_div.find("textarea")
		if textarea.contents:
			explanation = textarea.contents[0].strip()
		importance_input = question.find(id="question_{}_importance".format(qid))
		importance = importance_input["value"]
		public_input = question.find(id="public_{}".format(qid))
		public = public_input["value"] == "on"
		questions.append(Question(qid, question_text, public, importance, answers, explanation))
	return questions

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
	return int(count.contents[0])

def get_question_page(cj, opener, username, low):
	response = opener.open(kQuestionUrl.format(username) + "?low={}".format(low))
	questions = parse(response.read())
	return questions

def to_xml(questions):
	root = ET.Element("questions")
	for question in questions:
		attributes = {
			"id": question.qid,
			"importance": question.importance,
		}
		if question.public:
			attributes["public"] = "true"
		question_tag = ET.SubElement(root, "question", attributes)
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
	return ET.ElementTree(root)

if __name__ == "__main__":
	config = ConfigParser.SafeConfigParser()
	config.read(kConfigFile)
	cj = cookielib.CookieJar()
	opener = urllib2.build_opener(urllib2.HTTPRedirectHandler(), urllib2.HTTPHandler(), urllib2.HTTPSHandler(), urllib2.HTTPCookieProcessor(cj))
	username = config.get("login", "username")
	page = login(cj, opener, username, config.get("login", "password"))
	question_count = get_question_count(cj, opener, username)
	sys.stderr.write("Fetching {} questions\n".format(question_count))
	sys.stderr.flush()
	questions = list()
	for low in range(1, question_count, 10):
		questions.extend(get_question_page(cj, opener, username, low))
		sys.stderr.write(".")
		sys.stderr.flush()
	sys.stderr.write("\n")
	xml = to_xml(questions)
	xml.write(sys.stdout, encoding="UTF-8")
