class LLMTemplates:
    @staticmethod
    def prompt_analyze_news(data):
        prompt = \
"""Analyze Telegram message. Do not add your thought at the beginning and the end of the answer.
Desired output structure format:
[{"message_id": %MESSAGE_ID%, "priority": "%PRIORITY%", "category": "%CATEGORY%", "hashtags": "%HASHTAGS%", "country": "%COUNTRY%", "summary": "%SUMMARY%", "title": "%TITLE%"}]
Where:
%MESSAGE_ID% : Leave this unchanged.
%PRIORITY% : Choose from: 1, 2, 3, 4, 5. Where 1 is the lowest priority and 5 is the highest
%CATEGORY% : Provide a category like Politics, Economics, Law, Education, etc. Or N/A.
%HASHTAGS% : Generate from 1 to 3 relevant hashtags for the message or N/A.
%COUNTRY% : Specify the country the message is likely about (e.g., Global, USA, Europe, N/A).
%SUMMARY% : Write a concise and engaging summary of the message as if you were a skilled newsmaker.
%TITLE: Title for the message. No more than 6 words.
Please follow these instructions carefully for each Telegram message you process independently.
Messages in JSON format:"""
        prompt += data
        return prompt