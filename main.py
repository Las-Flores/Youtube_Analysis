from googleapiclient.discovery import build
import os
import warnings
warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true")
from dotenv import load_dotenv
import mysql.connector
from functions import scraping_data, install_thumbnails, read_text_from_thumbnails

#Load sensitive information from a .env file
load_dotenv()

#Connect to the mysql database
conn = mysql.connector.connect(
    host=os.getenv('host'),
    user=os.getenv('user'),
    password=os.getenv('password'),
    database=os.getenv('database'))
cursor = conn.cursor()

#Prepare the youtube API
youtube = build('youtube', 'v3', developerKey=os.getenv("API_KEY"))

#What queries does the API has to go through
#If the videos should be searched by popularity, relevance or viewCount
#How many videos per query are going to be scraped
#How old (in days) the videos should maximally be
queries = ['data science', 'data analysis', 'data engineering', 'data scientist', 'data analyst', 'data engineer', 'machine learning']
order = 'relevance' 
amount = 50
publishedAfter = 30 
videos = scraping_data(youtube=youtube, queries=queries, order=order, amount=amount, publishedAfter=publishedAfter, cursor=cursor, conn=conn)

install_thumbnails(videos=videos)
read_text_from_thumbnails(cursor=cursor, conn=conn)


conn.commit()
cursor.close()
conn.close()


