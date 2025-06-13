from googleapiclient.discovery import build
from datetime import datetime
from isodate import parse_duration
import datetime as dt
import pandas as pd
import easyocr
import requests
import os
from PIL import Image
import warnings
from dotenv import load_dotenv
import numpy as np
warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true")

load_dotenv()
youtube = build('youtube', 'v3', developerKey=os.getenv("API_KEY"))
queries = ['data science', 'data analysis', 'data engineering', 'data scientist', 'data analyst', 'data engineer', 'machine learning']

for query in queries:
    search_response = youtube.search().list(
        q=query,
        part='snippet',
        type='video',
        maxResults=50, 
        order='viewCount',
        relevanceLanguage='en',
        publishedAfter=(dt.datetime.now() - dt.timedelta(days=30)).isoformat() + 'Z',    
    ).execute()

    videos = []

    for item in search_response['items']:
        video_id = item['id']['videoId']
        channel = item['snippet']['channelTitle']
        title = item['snippet']['title']
        description = item['snippet']['description']
        
        date = datetime.strptime(item['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ")
        day = date.strftime("%Y-%m-%d")
        hour = date.strftime('%H:%M:%S')
        
        thumbnails = item['snippet']['thumbnails']
        thumbnail_url = thumbnails.get('high', thumbnails.get('default'))['url']
        
        channel_id = item['snippet']['channelId']
        statistics = youtube.channels().list(
        part='statistics',
        id=channel_id
        ).execute()
        stats = statistics['items'][0]['statistics']
        subscriber_count = stats.get('subscriberCount', 'Not available')
        
        location = youtube.channels().list(
        part='snippet',
        id=channel_id
        ).execute()
        channel_snippet = location['items'][0]['snippet']
        country = channel_snippet.get('country', 'Not specified')

        engagement = youtube.videos().list(
        part='statistics',
        id=video_id
        ).execute()
        engagement_stats = engagement['items'][0]['statistics']
        view_count = engagement_stats.get('viewCount', 'N/A')
        like_count = engagement_stats.get('likeCount', 'N/A')
        comment_count = engagement_stats.get('commentCount', 'N/A')
        
        details = youtube.videos().list(
        part='contentDetails',
        id=video_id
        ).execute()
        def convert_to_time(iso_duration):
            td = parse_duration(iso_duration)
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600 % 24
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        duration = convert_to_time(details['items'][0]['contentDetails']['duration'])
        
        top_comments = []

        try:
            response = youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=5,
                order='relevance'  
            ).execute()

            for idx, item in enumerate(response['items'], 1):
                top_comments.append(item['snippet']['topLevelComment']['snippet']['textDisplay'])

        except Exception as e:
            print(e)
            
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        videos.append({
            'title':title, 
            'channel':channel, 
            'subscriber_count':subscriber_count, 
            'day':day, 
            'hour':hour, 
            'description':description, 
            'view_count':view_count, 
            'like_count':like_count, 
            'comment_count':comment_count, 
            'top_comments':top_comments, 
            'url':url, 
            'thumbnail_url':thumbnail_url, 
            'country':country,
            'duration':duration})


    import mysql.connector
    conn = mysql.connector.connect(
        host=os.getenv('host'),
        user=os.getenv('user'),
        password=os.getenv('password'),
        database=os.getenv('database')
    )
    cursor = conn.cursor()

    def safe_int(val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0
        
    inserted_videos = 0
    inserted_channels = 0
    inserted_comments = 0

    for video in videos:
        # Check if channel already exists
        cursor.execute("SELECT id FROM Channels WHERE channel_name = %s", (video['channel'],))
        result = cursor.fetchone()
        
        if cursor.fetchone() is None:
            if result:
                channel_id = result[0]
            else:
                cursor.execute("""
                    INSERT INTO Channels (channel_name, subscriber_count, country)
                    VALUES (%s, %s, %s)
                """, (video['channel'], safe_int(video['subscriber_count']), video['country']))
                channel_id = cursor.lastrowid
                inserted_channels += 1
        
            cursor.execute("SELECT id FROM Videos WHERE video_url = %s", (video['url'],))
            if cursor.fetchone() is None:
                # Insert video
                cursor.execute("""
                    INSERT INTO Videos (
                        channel_id, title, description, day, hour, duration,
                        like_count, view_count, comment_count, video_url, thumbnail_url, query
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    channel_id,
                    video['title'],
                    video['description'],
                    video['day'],
                    video['hour'],
                    video['duration'],
                    safe_int(video['like_count']),
                    safe_int(video['view_count']),
                    safe_int(video['comment_count']),
                    video['url'],
                    video['thumbnail_url'],
                    query
                ))

            video_id = cursor.lastrowid
            inserted_videos += 1
        
        cursor.execute("SELECT id FROM Videos WHERE video_url = %s", (video['url'],))
        video_row = cursor.fetchone()
        if video_row:
            video_id = video_row[0]
            for comment in video['top_comments']:
                cursor.execute("""
                    INSERT INTO Comments (video_id, comment)
                    VALUES (%s, %s)
                """, (video_id, comment))
                inserted_comments += 1
    conn.commit()
os.makedirs("thumbnails", exist_ok=True)
image_urls = cursor.execute("""SELECT thumbnail_url FROM Videos""")
image_urls = cursor.fetchall()
for index, (url,) in enumerate(image_urls):
    response = requests.get(url)
    if response.status_code == 200:
        filename = fr'thumbnails/{url}'
        with open(filename, 'wb') as file:
            file.write(response.content)

reader = easyocr.Reader(['en'], gpu=False, verbose=False)
dfs = []
for img_url in os.listdir('thumbnails'):
    img_path = os.path.join('thumbnails', img_url)
    cursor.execute("""
        SELECT id FROM Videos WHERE thumbnail_url = %s
    """, (img_url,))
    img_id = cursor.fetchone()
    try:
        img = Image.open(img_path)
        img.verify()
        img = Image.open(img_path)  
        result = reader.readtext(np.array(img))
        result = [r for r in result if r[2] >= 0.5]
        img_df = pd.DataFrame(result, columns=['bbox', 'text', 'conf'])
        img_df['img_id'] = img_id[0]
        img_df['img_url'] = img_url
        dfs.append(img_df)
    except (IOError, SyntaxError, FileNotFoundError) as e:
        print(f"Skipping corrupted or missing image: {img_path} - {e}")
thumbnails = pd.concat(dfs)

for _, row in thumbnails.iterrows():
    if row['img_id']:
        cursor.execute("""
            INSERT INTO thumbnail_text (video_id, text, coordinates, confidence)
            VALUES (%s, %s, %s, %s)
        """, (row['img_id'], row['text'], str(row['bbox']), row['conf']))
        conn.commit()
    else:
        print(f"No video found for thumbnail ID: {row['img_id']}")

print(f"\n✅ Scraping finished:")
print(f"• Inserted videos: {inserted_videos}")
print(f"• Inserted channels: {inserted_channels}")
print(f"• Inserted comments: {inserted_comments}")

conn.commit()
cursor.close()
conn.close()