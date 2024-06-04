import requests
import json
import feedparser
import sqlite3
from tqdm import tqdm
from youtube_transcript_api import YouTubeTranscriptApi
import youtube_transcript_api
from ollama import Client
from . import systemPrompts
from threading import Thread
import pickle

class ThreadWithReturnValue(Thread):
    
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None

    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args,
                                                **self._kwargs)
    def join(self, *args):
        Thread.join(self, *args)
        return self._return

feedUrl:str='https://www.youtube.com/feeds/videos.xml?channel_id={channelId}'
transcriptAPI='https://transcriptextractor.com/api/transcripts'

client = Client(host='http://localhost:11434')
conn=sqlite3.connect("./db.sqlite3")

conn.execute("""CREATE TABLE IF NOT EXISTS channel (channel_id TEXT , name TEXT)""")
conn.execute("CREATE TABLE IF NOT EXISTS latest_video (channel_id TEXT,video_id TEXT,upload_timestamp TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS video (video_id TEXT ,channel_id TEXT , summary TEXT, value TEXT)")
conn.commit()

channelIdList=conn.execute("SELECT channel_id, name FROM channel").fetchall()

# newVideos={}
# for channelId,channelName in tqdm(channelIdList,desc="New Video LookUp"):
#     videoList=[]
#     parsedData=feedparser.parse(feedUrl.format(channelId=channelId))
#     for index,entry in (enumerate(parsedData["entries"])):
#         if index!=0:#*DEBUG
#             break#*DEBUG

#         if latestVideoId:=conn.execute(f"SELECT video_id FROM latest_video WHERE channel_id='{entry["yt_channelid"]}'").fetchone():
#             if latestVideoId!=entry["yt_videoid"]:
#                 conn.execute(f"UPDATE latest_video SET video_id='{entry['yt_videoid']}',upload_timestamp='{entry['published']}' WHERE channel_id='{entry['yt_channelid']}'")
#                 videoList.append(entry["yt_videoid"])
#             else:
#                 break
#         else:
#             conn.execute(f"INSERT INTO latest_video (video_id,channel_id,upload_timestamp) VALUES ('{entry['yt_videoid']}','{entry['yt_channelid']}','{entry['published']}')")
#             videoList.append(entry["yt_videoid"])
#             break
#     newVideos[channelId]=videoList
#     conn.commit()
#     # break #*DEBUG


# videoTranscript={}
# for channelId,videoIds in tqdm(newVideos.items(),desc="Fetch Transcript"):
#     vTranscript={}
#     for videoId in videoIds:
#         try:
#             transcript:youtube_transcript_api._transcripts.Transcript=YouTubeTranscriptApi.list_transcripts(videoId).find_transcript(['en','hi'])
#             if transcript.language_code!='en':
#                 transcript=transcript.translate("en")
#             t=transcript.fetch()
#             vTranscript[videoId]=" ".join([text['text'] for text in t])
#         except Exception as e:
#             vTranscript[videoId]=str(e)
#             # raise e
#     videoTranscript[channelId]=vTranscript
#     # break#*DEBUG

modelfile='''
FROM {baseModel}
SYSTEM """
{systemPrompt}
"""
'''
modelPromptDict={
    "Summary":systemPrompts.createSummary,
    "MainIdea":systemPrompts.extractMainIdea,
    "Insight":systemPrompts.extractInsight,
    "Wisdom":systemPrompts.extractWisdom,
    "Value":systemPrompts.extractRealValue
}
baseModel="llama3:8b-instruct-q6_K"
modelNames={}

for name,prompt in modelPromptDict.items():
    print(baseModel+":"+name)
    client.create(model=baseModel.split(":")[0]+":"+name, modelfile=modelfile.format(baseModel=baseModel,systemPrompt=prompt))
    modelNames[name]=baseModel.split(":")[0]+":"+name

# pickle.dump(videoTranscript,open('data.pickle',"wb"))
videoTranscript=pickle.load(open('data.pickle',"rb"))

for channelId,vTranscript in tqdm(videoTranscript.items(),desc="AI summarization"):
    for videoId,transcript in vTranscript.items():
        if not conn.execute(f"SELECT video_id FROM video WHERE video_id='{videoId}'").fetchone():
            res=""""""
            threads={}
            for name,modelName in modelNames.items():
                if name=="Value":
                    continue
                t=ThreadWithReturnValue(target=lambda mdlName,txt: client.generate(mdlName,txt)['response'],args=(modelName,transcript))
                t.start()
                threads[name]=t

            for name,thread in threads.items():
                response=thread.join()
                res+=f"#{name.upper()}\n{response}\n\n"
            value=client.generate(modelNames["Value"],res)['response']
            query=f"INSERT INTO video (video_id,channel_id,summary,value) VALUES ('{videoId}','{channelId}', '{res.replace("'","''")}' , '{value.replace("'","''")}')"
            conn.execute(query)
            conn.commit()
            # break#*DEBUG
conn.close()
