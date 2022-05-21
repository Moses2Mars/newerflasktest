from flask import Flask
from flask import request
from resume_parser import resumeparse
import numpy as np
import docx
from docx import Document
skillsData = np.load("finalDataTags.npy")
import docx2txt
import pdfplumber
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer
import string
import spacy
nlp = spacy.load("en_core_web_sm")


app = Flask(__name__)

@app.route('/')
def hello():
    return '<h1>Hello, World!</h1>'

@app.route('/cv-form', methods=['POST'])
async def form_example():
    if request.method == 'POST':
        #job_description is already a string, to be compared with the CV
        job_description = request.form.get('job_description')
        
        #CV file from the request
        user_cv = request.files['file']
        extension = user_cv.filename.split('.')

        #if type is PDF
        if extension[-1] == 'pdf':
            #change from docx format to text (string) format
            resume = readFromPDF(user_cv)
        else: 
            #if type is doc/docx
            resume = docx2txt.process(user_cv)

        #clean both the resume and the job description
        cleaned_resume = cleanString(resume)
        cleaned_job_description = cleanString(job_description)

        wordMatch = checkWordMatchScore(cleaned_resume, cleaned_job_description)
        #save them both as docx files
        buildDocxFile(cleaned_resume, "resume.docx")
        buildDocxFile(cleaned_job_description, 'job_description.docx')

        #parse and math the resume with the job description
        data = parseAndMatchResume("resume.docx","job_description.docx", wordMatch)

        return str(data)

def readFromPDF(file): 
    text = ''
    with pdfplumber.open(file) as pdf:
        for pdf_page in pdf.pages:
            text += pdf_page.extract_text()
    return text

def buildDocxFile(data, filePath):
    document = Document()
    p = document.add_paragraph(data)
    document.save(filePath)

def parseAndMatchResume(resumePath, jobPath, wordMatch):
    rawResultsResume, rawResultsJob = getResults(resumePath, jobPath)
    rawResultsResume["scores"] = calculatePoints(rawResultsResume, rawResultsJob, wordMatch)
    rawResultsResume["matchScore"] = calculateMatch(rawResultsResume["scores"])

    finalResults = finalArrangeData(rawResultsResume)
    return finalResults

def getResults(resume_path, job_description_path):
    resumeData = resumeparse.read_file(resume_path)
    resumeData["skills"] = parseSkills(resumeData["skills"])
    #print("Resume Skills:", resumeData["skills"])

    jobData = resumeparse.read_file(job_description_path)
    jobData["skills"] = parseSkills(jobData["skills"])
    #print("Job Skills:", jobData["skills"])

    skillsRes = finalizeSkillsDisplay(resumeData["skills"], jobData["skills"])
    resumeData["skillsData"] = skillsRes

    miscResults = finalizeMetaResults(resume_path, job_description_path, resumeData)

    resumeData["meta"] = miscResults

    return resumeData, jobData

def calculatePoints(resumeData, jobData, wordMatch):
    skills = checkSkillsScore(resumeData["skills"], jobData["skills"])
    data = {
        "skills": skills,
        "wordMatch": wordMatch,
    }
    return data

def checkWordMatchScore(resume_text, job_description_text):
    #making a list of both the resume and job description
    text_list = [resume_text, job_description_text]

    # Convert a collection of text documents to a matrix of token counts 
    cv = CountVectorizer()
    count_matrix = cv.fit_transform(text_list)

    # Cosine similarity is a metric used to measure how similar the documents are irrespective of their size. 
    # Mathematically, it measures the cosine of the angle between two vectors projected in a multi-dimensional space. 
    # The cosine similarity is advantageous because even if the two similar documents are far apart by the Euclidean distance 
    # (due to the size of the document), chances are they may still be oriented closer together. 
    # The smaller the angle, the higher the cosine similarity.
    matchPercentage = cosine_similarity(count_matrix)[0][1] * 100

    # round to two decimal
    matchPercentage = round(matchPercentage, 2) 

    return matchPercentage

def checkSkillsScore(resumeSkills, JobSkills):
    resumeSkills = [skill.lower() for skill in resumeSkills]
    JobSkills = [skill.lower() for skill in JobSkills]
    eScore = 0
    for jSkill in JobSkills:
        if jSkill in resumeSkills:
            eScore += 1
            
    return {"exists": eScore, "not-exists" : len(JobSkills) - eScore, "total" : len(JobSkills)}

def calculateMatch(score):
    skillsMatchScore = score["skills"]["exists"] / score["skills"]["total"] * 1.3
    wordsMatchScore = score["wordMatch"] / 100

    # if copy pasted the job description
    if(wordsMatchScore >= 1):
        wordsMatchScore = 0.1
    else: 
        wordsMatchScore = wordsMatchScore * 1.3
    
    if(skillsMatchScore >= 1):
        skillsMatchScore = 0.1
    else: 
        skillsMatchScore = skillsMatchScore * 1.3

    totalScore = skillsMatchScore + wordsMatchScore

    if(totalScore >= 0.95):
        totalScore = 0.95

    return round(totalScore * 100)

def finalArrangeData(resumeData):
    data = {}
    data["totalScore"] = resumeData["matchScore"]
    # data["scores"] = resumeData["scores"]
    # data["skillsData"] = resumeData["skillsData"]

    return data["totalScore"]

def parseSkills(skills):
    skillsFinal = []
    for skill in skills:
        lowerSkill = skill.lower()
        if lowerSkill in skillsData:
            skillsFinal.append(skill)
    return skillsFinal

def finalizeSkillsDisplay(resumeSkills, JobSkills):
    fSkills = {}
    resumeSkills = [skill.lower() for skill in resumeSkills]

    JobSkills = [skill.lower() for skill in JobSkills]
    eSkills = 0
    for skill in resumeSkills:
        if skill not in JobSkills:
            fSkills[skill] = {
                "wanted": False,
                "exists": True
            }
        else:
            eSkills += 1
            fSkills[skill] = {
                "wanted": True,
                "exists": True
            }
    for skill in JobSkills:
        if skill not in resumeSkills:
            fSkills[skill] = {
                "wanted": True,
                "exists": False
            }
        else:
            fSkills[skill] = {
                "wanted": True,
                "exists": False
            }
    return fSkills

def finalizeMetaResults(ResumePath, JobPath, ResumeData):
    meta = {}
    text = getTextFromDocx(ResumePath)
    meta["length"] = len(text)
    textJob = getTextFromDocx(JobPath)

    meta["educationHeading"] = True if checkEducation(text) else False    
    meta["workExperienceHeading"] = True if checkExperience(text) else False
    meta["educationRequirements"] = True if checkEducation(textJob) else False
    ResumeData["skillsData"] = countWords(ResumeData["skillsData"], text.lower(), textJob.lower())
    
    return meta

def getTextFromDocx(filename):
    doc = docx.Document(filename)
    fullText = []
    for para in doc.paragraphs:
        fullText.append(para.text)
    return '\n'.join(fullText)

def checkEducation(txt):
    edu = ["Education", "Degree"]
    for e in edu:
        if e.lower() in txt.lower():
            return True
    return False

def checkExperience(txt):
    exp = ["Experience", "Work Experience"]
    for e in exp:
        if e.lower() in txt.lower():
            return True
    return False

def checkEducation(txt):
    edu = ["Education", "Degree"]
    for e in edu:
        if e.lower() in txt.lower():
            return True
    return False

def countWords(skills, ResumeText, JobText):
    meta = {}
    for skill, val in skills.items():
        skillTest = skill.lower()
        meta[skill] = {
            "ResumeCount" : ResumeText.count(skillTest),
            "JobCount" : JobText.count(skillTest),
            "wanted" : val["wanted"],
            "exists" : val["exists"]
        }
    return meta

def cleanString(stringer): 
    cleaned_string = ''.join(c for c in stringer if valid_xml_char_ordinal(c))

    tokens = word_tokenize(cleaned_string)

    # remove punctuation from each word
    table = str.maketrans(string.punctuation, ' ' * len(string.punctuation))
    stripped = [w.translate(table) for w in tokens]


    # filter out stop words    
    stop_words = set(stopwords.words('english'))
    words = [w for w in stripped if not w in stop_words]
    words = ' '.join(words)

    return str(words)

def valid_xml_char_ordinal(c):
    codepoint = ord(c)
    # conditions ordered by presumed frequency
    return (
        0x20 <= codepoint <= 0xD7FF or
        codepoint in (0x9, 0xA, 0xD) or
        0xE000 <= codepoint <= 0xFFFD or
        0x10000 <= codepoint <= 0x10FFFF
        )