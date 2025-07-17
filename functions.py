from googleapiclient.discovery import build
from datetime import datetime
from isodate import parse_duration
import datetime as dt
import requests
import os
import easyocr
from PIL import Image
import numpy as np
import pandas as pd
import json

def scraping_data(youtube, queries, order, amount, publishedAfter, cursor, conn):
    videos = []
    for query in queries:
        search_response = youtube.search().list(
            q=query,
            part='snippet',
            type='video',
            maxResults=amount, 
            order=order,
            relevanceLanguage='en',
            publishedAfter=(dt.datetime.now() - dt.timedelta(days=publishedAfter)).isoformat() + 'Z',    
        ).execute()

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
            cursor.execute("SELECT id FROM channels WHERE channel_name = %s", (video['channel'],))
            result = cursor.fetchone()
            
            if cursor.fetchone() is None:
                if result:
                    channel_id = result[0]
                else:
                    cursor.execute("""
                        INSERT INTO channels (channel_name, subscriber_count, country)
                        VALUES (%s, %s, %s)
                    """, (video['channel'], safe_int(video['subscriber_count']), video['country']))
                    channel_id = cursor.lastrowid
                    inserted_channels += 1

                cursor.execute("SELECT id FROM videos WHERE video_url = %s", (video['url'],))
                if cursor.fetchone() is None:
                    # Insert video
                    cursor.execute("""
                        INSERT INTO videos (
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

            cursor.execute("SELECT id FROM videos WHERE video_url = %s", (video['url'],))
            video_row = cursor.fetchone()
            if video_row:
                video_id = video_row[0]
                for comment in video['top_comments']:
                    cursor.execute("""
                        INSERT INTO comments (video_id, comment)
                        VALUES (%s, %s)
                    """, (video_id, comment))
                    inserted_comments += 1
        print(f"\n✅ Scraping finished for {query}:")
        print(f"• Inserted videos: {inserted_videos}")
        print(f"• Inserted channels: {inserted_channels}")
        print(f"• Inserted comments: {inserted_comments}")
        conn.commit()
    return videos

def install_thumbnails(videos, max_retries=3):
    folder = "thumbnails"
    os.makedirs(folder, exist_ok=True)
    
    failed_downloads = []
    
    for video in videos:
        thumbnail_url = video['thumbnail_url']
        video_id = thumbnail_url.replace('https://i.ytimg.com/vi/', '').split('/')[0]
        filename = f"{video_id}.jpg"
        filepath = os.path.join(folder, filename)
        
        # Skip if already exists and is valid
        if os.path.exists(filepath):
            try:
                # Verify the image isn't corrupted
                with Image.open(filepath) as img:
                    img.verify()
                print(f"Skipping {filename} (valid file exists)")
                continue
            except (IOError, SyntaxError):
                print(f"Existing file corrupted, redownloading: {filename}")
                os.remove(filepath)
        
        # Download with retries
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    thumbnail_url,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=10
                )
                response.raise_for_status()  # Raises exception for 4XX/5XX status
                
                # Verify the downloaded content is actually an image
                try:
                    with Image.open(BytesIO(response.content)) as img:
                        img.verify()
                    
                    # Save the file
                    with open(filepath, 'wb') as file:
                        file.write(response.content)
                    print(f"Successfully downloaded: {filename}")
                    break
                except (IOError, SyntaxError) as img_error:
                    print(f"Downloaded invalid image (attempt {attempt+1}): {img_error}")
                    if attempt == max_retries - 1:
                        failed_downloads.append(video_id)
            except (requests.RequestException, Exception) as e:
                print(f"Download failed (attempt {attempt+1}) for {filename}: {e}")
                if attempt == max_retries - 1:
                    failed_downloads.append(video_id)
                time.sleep(1)  # Brief pause before retry
    
    # Report failures
    if failed_downloads:
        print(f"\nFailed to download {len(failed_downloads)} thumbnails:")
        for vid in failed_downloads:
            print(f"- Video ID: {vid}")
    
    return failed_downloads
    
def read_text_from_thumbnails(cursor, conn):
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    dfs = []

    cursor.execute("SELECT DISTINCT video_id FROM thumbnail_text")
    existing_videos = {row[0] for row in cursor.fetchall()}

    for img in os.listdir('thumbnails'):
        video_id = os.path.splitext(img)[0]
        img_url = f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
        img_path = f'thumbnails/{img}'

        cursor.execute("""
            SELECT id FROM videos WHERE thumbnail_url = %s
        """, (img_url,))
        img_id = cursor.fetchone()
        if not img_id or img_id[0] in existing_videos:
            continue
        try:
            img = Image.open(img_path)
            img_copy = img.copy()
            img_copy.verify()
            result = reader.readtext(np.array(img))
            result = [r for r in result if r[2] >= 0.5]
            if not result:  # If OCR found nothing
                # Insert a record indicating no text was found
                cursor.execute("""
                    INSERT INTO thumbnail_text 
                    (video_id, img_url, text, coordinates, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                """, (img_id[0], img_url, None, None, None))
                continue
            img_df = pd.DataFrame(result, columns=['bbox', 'text', 'conf'])
            img_df['img_name'] = os.path.basename(img_path)
            img_df['img_url'] = img_url
            img_df['video_id'] = img_id[0] if img_id else None
            dfs.append(img_df)
        except Exception as ocr_error:
            print(f"OCR failed for {img_path}: {ocr_error}")
            # Insert failure record
            cursor.execute("""
                INSERT INTO thumbnail_text 
                (video_id, img_url, text, coordinates, confidence)
                VALUES (%s, %s, %s, %s, %s)
            """, (img_id[0], img_url, None, None, None))
        except (IOError, SyntaxError, FileNotFoundError) as e:
            print(f"Skipping corrupted or missing image: {img_path} - {e}")


    if dfs:
        thumbnails = pd.concat(dfs, ignore_index=True)
        for _, row in thumbnails.iterrows():
            try:
                bbox_array = np.array(row['bbox'])
                bbox_json = json.dumps(bbox_array.tolist())            
                cursor.execute("""
                    INSERT INTO thumbnail_text 
                    (video_id, img_url, text, coordinates, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                """, (row['video_id'], row['img_url'], row['text'], bbox_json, row['conf']))
            except Exception as e:
                print(f"Error inserting row: {e}")
    
    conn.commit()
