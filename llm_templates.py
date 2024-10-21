class LLMTemplates:
    @staticmethod
    def prompt_analyze_news(data):
        prompt = \
""""Analyze Telegram message. Do not add your thought at the beginning and the end of the answer.
Here's the desired output structure:
[{"message_id": %MESSAGE_ID%, "priority": "%PRIORITY%", "category": "%CATEGORY%", "hashtags": "%MAIN_TOPIC%", "country": "%COUNTRY%", "thoughts": "%YOUR_THOUGHTS%"}]
Where:
%MESSAGE_ID% : Leave this unchanged.
%PRIORITY% : Choose from: High, Medium-High, Medium, Medium-Low, Low
%CATEGORY% : Provide a category like Politics, Economics, Law, Education, etc.
%MAIN_TOPIC% : Generate 1-3 relevant hashtags for the message.
%COUNTRY% : Specify the country the message is likely about (e.g., Global, USA, Europe, N/A).
%YOUR_THOUGHTS% : Write a concise and engaging summary of the message as if you were a skilled newsmaker.
Please follow these instructions carefully for each Telegram message you process.

This prompt clearly defines:
The Goal: Analyze and summarize Telegram messages.
The Output Format: JSON structure with specific fields.
Field Definitions: Explains what each placeholder means.
Example Hashtags: Shows how to generate relevant hashtags.
Newsmaker Tone: Emphasizes the desired writing style.
Messages in JSON format:"""
        prompt += data
        return prompt