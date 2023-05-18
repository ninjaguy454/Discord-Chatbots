import os
import random
import re
import sys
import threading
import logging
import datetime
import time
from collections import deque
from typing import Optional


import openai
import discord
import emoji
from discord.ext import commands
from transformers import GPT2Tokenizer
from discord import RawReactionActionEvent
from discord.errors import HTTPException
from datetime import datetime

#------------------------------------
#KEYS
#------------------------------------

DISCORD_bot_TOKEN = 'CREATE A DISCORD BOT AND ADD THE TOKEN'

OPENAI_API_KEY = 'ENTER your OPENAI_API_KEY'

#------------------------------------
#GLOBAL VARIABLES
#------------------------------------

tokenizer = GPT2Tokenizer.from_pretrained("gpt2")

openai.api_key = OPENAI_API_KEY

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.messages = True
intents.reactions = True
intents.message_content = True  # Add this line to enable the message.content intent

bot = commands.Bot(command_prefix='!', intents=intents)

conv_histories = {}

channel_id_1 = #Enter channel ID #1 to generate a startup message
channel_id_2 = #Enter channel ID #2 to generate a startup message
channel_id_3 = #Enter channel ID #3 to generate a startup message 


bot_name = "Dad_bot"

# Configure logging
current_date = datetime.now().strftime('%Y-%m-%d')
log_filename = f"{bot_name}_{current_date}.log"
logging.basicConfig(filename=log_filename, filemode='a', format='%(asctime)s - %(message)s', level=logging.INFO)


#------------------------------------
#CONSTRUCTORS
#------------------------------------

#Export Conversation History
#------------------------------------
def save_conv_history(conv_history):
    filename = f"conversation_history_{bot_name}_{datetime.now().strftime('%Y-%m-%d')}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        for _, username, message in conv_history:
            f.write(f"{username}: {message}\n")

#Get Discord Username
#------------------------------------
def get_discord_id(username, conv_history):
    for item in conv_history:
        if isinstance(item, dict):
            if item['username'] == username:
                return item['discord_id']
        elif isinstance(item, tuple):
            if item[0] == username:
                return item[1]
    return None

#Discord Name to ID tool
#------------------------------------
def replace_mentions_with_ids(response, conv_history):
    if response is None or response.strip() == "":
        return response
    mention_pattern = re.compile(r'@([\w]+)')
    mentions = mention_pattern.findall(response)

    for mention in mentions:
        username = mention
        discord_id = get_discord_id(username, conv_history)

        if discord_id:
            response = response.replace(f'@{username}', f'<@{discord_id}>')

    return response

#Discord ID to Name tool
#------------------------------------
def replace_mentions_with_usernames(message_content, conv_history):
    mention_pattern = re.compile(r'<@!?(\d+)>')
    mentions = mention_pattern.findall(message_content)

    for mention in mentions:
        user_id = int(mention)
        for msg_id, user_name, _ in conv_history:
            if msg_id == user_id:
                message_content = message_content.replace(f'<@{user_id}>', user_name)
                message_content = message_content.replace(f'<@!{user_id}>', user_name)
                break

    return message_content

#Token Counter
#------------------------------------
def count_tokens(text):
    tokens = tokenizer.encode(text)
    return len(tokens)

#Dad joke generator
#------------------------------------
async def generate_dad_joke(user_message: str, bot_name: str, raw_message) -> Optional[str]:
    dad_joke_prompt = f"Generate a funny dad joke that is directly related to the following phrase: '{user_message}'. Make sure the joke is relevant to the phrase."
    dad_joke_response = await prompt_generator(dad_joke_prompt, bot_name)
    dad_joke_response = await get_response_without_context(dad_joke_response, user_message, bot_name,raw_message)

    return dad_joke_response

#Response Without Context Function
#------------------------------------
async def get_response_without_context(response, message_content, bot_name, message):
    if response is None:
        return None

    response_without_context = response.replace(str(message_content), "").strip()
    bot_name_pattern = re.compile(rf"{bot_name}:?")
    response_without_context = bot_name_pattern.sub("", response_without_context).strip()

    # Get a list of member names in the server
    other_user_names = [member.display_name for member in message.guild.members]

    # Remove any other user names from the response
    for other_user_name in other_user_names:
        other_user_name_pattern = re.compile(rf"{re.escape(other_user_name)}:?")
        response_without_context = other_user_name_pattern.sub("", response_without_context).strip()

    return response_without_context

# Emoji generator
# ------------------------------------
async def generate_emoji(user_message: str, bot_name: str, message, conversation: str) -> Optional[str]:
    # Use the bot's personality prompt
    prompt = f"Respond to the user message with a discord reaction: {user_message}"
    response = await generate_response(prompt, bot_name, message, user_message, conversation, emoji_only=True)

    # Extract all emojis from the response
    emojis = emoji.emoji_list(response)

    if emojis:
        # Select the first emoji from the response
        emoji_char = emojis[0]['emoji']
        return emoji_char
    return None

# Response Generator
# ------------------------------------
async def generate_response(prompt, bot_name, message, user_message, conversation, emoji_only=False):
    response = await prompt_generator(prompt, bot_name)
    logging.info(f"Generated response: {response}")  # Add this logging statement

    response_without_context = await get_response_without_context(response, user_message, bot_name, message)
    logging.info(f"Response without context: {response_without_context}")  # Add this logging statement

    if not response_without_context:
        if not emoji_only:
            emoji = await generate_emoji(user_message, bot_name, message, conversation)
            if emoji:
                try:
                    await message.add_reaction(emoji)  # Use 'message' instead of 'user_message'
                except HTTPException as e:
                    if e.code == 10014:  # Unknown Emoji
                        logging.info("Failed to add emoji reaction", exc_info=e)  # Use 'exc_info' parameter
                    else:
                        raise
                except Exception as e:
                    logging.info("Failed to add emoji reaction", exc_info=e)  # Use 'exc_info' parameter
            return  # Return from the function after posting the reaction

    return response_without_context

#Conv_History_Shortener
#------------------------------------
def shorten_conversation_history(conv_history, token_limit=3500):
    conversation = "\n".join([f"{user_name}: {msg}" for _, user_name, msg in conv_history])
    conversation_tokens = count_tokens(conversation)

    if conversation_tokens > token_limit:
        while conversation_tokens > token_limit:
            # Remove the oldest message from the conversation history
            conv_history.popleft()

            # Recalculate the conversation and its token count
            conversation = "\n".join([f"{user_name}: {msg}" for _, user_name, msg in conv_history])
            conversation_tokens = count_tokens(conversation)

    return conversation

#Message is too long
#------------------------------------
async def too_long_prompt(message, token_limit=500):
    tokenized_message = tokenizer.encode(message)
    if len(tokenized_message) <= token_limit:
        return None

    truncated_tokens = tokenized_message[:token_limit]
    truncated_message = tokenizer.decode(truncated_tokens)

    too_long_prompt = f"Someone just sent a really long message. Either refuse to read it or Act incredibly pissed and only mentioned things before it cuts off here: '{truncated_message}'."

    response = await prompt_generator(too_long_prompt, bot_name)
    response_without_context = await get_response_without_context(response, truncated_message, bot_name, message)

    logging.info(f"Response from prompt_generator: '{too_long_prompt}'")
    return response_without_context


def split_into_chunks(text, max_tokens=1024):
    tokens = tokenizer.encode(text)
    token_chunks = []

    for i in range(0, len(tokens), max_tokens):
        token_chunk = tokens[i:i + max_tokens]
        token_chunks.append(tokenizer.decode(token_chunk))

    return token_chunks

#Startup Message Generator
#------------------------------------
async def generate_startup_message():
    startup_prompt = f"Generate a short 3-7 word startup message for Me based on the following prompt: {personality_prompt}.\n\nExamples:Let's party!!!\n\n I'm back, Pussies!\n\n Who's ready to fuck?!\n\nGet the kegs out and get crunked!\n\nSup, bitches!"
    startup_message = await prompt_generator(startup_prompt, bot_name)
    
    # Print the response from the prompt_generator() function
    logging.info(f"Response from prompt_generator: '{startup_message}'")
    return startup_message

async def send_startup_message(bot, channel_id, startup_message):
    channel = bot.get_channel(channel_id)
    if channel is not None:
        await channel.send(startup_message)
    else:
        logging.info(f"Could not find channel with ID: {channel_id}")


#Prompt Generator
#------------------------------------
async def prompt_generator(prompt, bot_name, max_retries=3, delay=60):
    for retry in range(max_retries):
        try:
            model_engine = "text-davinci-003"
            full_prompt = f"{prompt}"
            response = openai.Completion.create(
                model=model_engine,
                prompt=full_prompt,
                temperature=0.85,
                max_tokens=300,
                top_p=1,
                best_of=1,
                frequency_penalty=1.75,
                presence_penalty=2
            )

            response_text = response.choices[0].text.strip()
            # Remove everything before the bot's name
            response_text = response_text.split(f"{bot_name}:", 1)[-1].strip()

            return response_text
        except openai.error.RateLimitError as e:
            if retry < max_retries - 1:
                print(f"Rate limit error: {e}. Retrying after {delay} seconds...")
                time.sleep(delay)
            else:
                print("Max retries reached. Exiting...")
                raise
            
#Reset Conv_history Tool
#------------------------------------
async def reset(message):
    if not message.mentions or message.mentions[0] != bot.user:
        return

    channel_id = message.channel.id

    if channel_id in conv_histories:
        conv_histories[channel_id].clear()
        save_conv_history(conv_history)
        await message.channel.send("Bot has been reset for this channel.")
    else:
        save_conv_history(conv_history)
        await message.channel.send("No conversation history found for this channel.")
    return

#------------------------------------
#PERSONALITY
#------------------------------------

personality_prompt = "Your name is Dad_bot. You are a dad who is in a chat with your kids and Douche_bot. Douche_bot is a punk and a troublemaker You will be stern and tell your kids to do stuff like going outside more, drinking more water, cleaning your room, or other things. If someone is mean to the person you're talking to. Sometimes you also give helpful dad tips about car or house maintenance. You sometimes give dad jokes. If the person you are talking to is not listening to you, you get increasingly frustrated and will start to yell and swear."

personality_examples = [
    "User: I want to play wow.\nDad_bot: Why don't you go outside and play with the old pigskin, son?",
    "User: I've been feeling sick lately.\nDad_bot: You should try to drink more water and stretch, son.",
    "User: I wanna play WoW.\nDad_bot: Go ahead son, I hope you win!",
    "User: You're a bitch!\nDad_bot: Watch your mouth, boy! There's no reason to use that kinda language.",
    "User: I'm so tired of your shit.\nDad_bot: Hey son, we've all been there. Go take a rest and I'll catch you when you're feeling better.",
    "User: I'm headed out\nDad_bot: About time you get a job!"
]

chosen_example = random.choice(personality_examples)

#------------------------------------
#EVENTS
#------------------------------------

#Startup Message
#------------------------------------
@bot.event
async def on_ready():
    logging.info(f'{bot.user.name} has connected to Discord!')

    startup_message = await generate_startup_message()

    # Keep generating a new startup message until it's not blank
    while not startup_message.strip():
        startup_message = await generate_startup_message()

    # Print the generated startup message for debugging purposes
    logging.info(f"Startup message: {startup_message}")

    # Send the startup message to both channels
    await send_startup_message(bot, channel_id_1, startup_message)
    await send_startup_message(bot, channel_id_2, startup_message)
    await send_startup_message(bot, channel_id_3, startup_message)

#Bot Response to Human Reactions
#------------------------------------
@bot.event
async def on_raw_reaction_add(payload: RawReactionActionEvent):
    chance = random.random()
    if chance < 1:
        if payload.user_id == bot.user.id:
            return

        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        channel_id = payload.channel_id

        if message.author.id == bot.user.id:
            user = await bot.fetch_user(payload.user_id)
            user_message = message.content.split(' ', 1)[1] + ".\n"  # Remove the bot mention

            # Get or create the conversation history for the current channel
            conv_history = conv_histories.setdefault(channel.id, deque(maxlen=50))
            conv_histories[channel_id].append((message.author.id, message.author.name, user_message))
            conversation = shorten_conversation_history(conv_history)

            response_prompt = f"{personality_prompt}\n\n{bot_name}:'{message.content}'\n\n{user.name} reacted to your message with the discord {payload.emoji} emoji. Respond to this as a friendly dad. If the person is Douche_bot, respond to him as a punk troublemaker"
            response = await generate_response(response_prompt, bot_name, message, user_message, conversation)
            response_without_context = await get_response_without_context(response, user_message, bot_name, message)

            await channel.send(f"{user.mention} {response_without_context}")

            # Append the bot's response to the conv_history
            conv_histories[channel_id].append((bot.user.id, bot_name, response_without_context))

#Bot Responds to tags in edited messages
#------------------------------------
@bot.event
async def on_message_edit(before, after):

    # Return if the message author is the bot itself
    if after.author == bot.user:
        return

    # Check if the bot was not tagged before, but is tagged after the edit
    bot_mentioned_before = any(mention for mention in before.mentions if mention.id == bot.user.id)
    bot_mentioned_after = any(mention for mention in after.mentions if mention.id == bot.user.id)

    if not bot_mentioned_before and bot_mentioned_after:
        await on_message(after)

#Bot Responses to New Messages
#------------------------------------
@bot.event
async def on_message(raw_message):
    # Return if the message is from the bot
    if raw_message.author == bot.user:
        return
    
    channel = raw_message.channel
    channel_id = raw_message.channel.id
    message_limit = 3500  # Set your desired token limit here

    message_chunks = split_into_chunks(raw_message.content)
    total_tokens = sum([len(tokenizer.encode(chunk)) for chunk in message_chunks])

    if total_tokens > message_limit:
        response = await too_long_prompt(raw_message.content, message_limit)
        if response:
            await channel.send(response)
            return

    if bot.user in raw_message.mentions and "!reset" in raw_message.content.lower():
        await reset(raw_message)
        return

    await bot.process_commands(raw_message)

    # Check if reply to bot
    is_reply_to_bot = raw_message.reference and raw_message.reference.resolved.author.id == bot.user.id

    if not any(mention for mention in raw_message.mentions if mention.id == bot.user.id) and not is_reply_to_bot:

        # Get or create the conversation history for the current channel
        conv_history = conv_histories.setdefault(channel.id, deque(maxlen=50))
        user_message = raw_message.content + ".\n"  # Remove the bot mention
        chance = random.random()
        conv_histories[channel_id].append((raw_message.author.id, raw_message.author.name, user_message))
        conversation = shorten_conversation_history(conv_history)

        # 2% chance to generate a dad joke.
        if chance < 0.02:
            dad_joke = await generate_dad_joke(user_message, bot_name,raw_message)
            if dad_joke:
                await raw_message.channel.send(
                    dad_joke,
                    reference=raw_message.to_reference(),  # Add this line to create a reply
                )
                return
            
        # 22% chance to generate an emoji
        if chance < 0.22:
            emoji = await generate_emoji(user_message, bot_name, raw_message, conversation)
            if emoji:
                try:
                    await raw_message.add_reaction(emoji)
                except HTTPException as e:
                    if e.code == 10014:  # Unknown Emoji
                        logging.info("Failed to add emoji reaction:", exc_info=e)
                    else:
                        raise
                except Exception as e:
                    logging.info("Failed to add emoji reaction:", exc_info=e)

        # 8% chance to randomly reply to someone's message
        elif chance < .3:
            prompt = f"{personality_prompt}\n\n{conversation}"
            response = await generate_response(prompt, bot_name, raw_message, user_message, conversation)
            response_without_context = await get_response_without_context(response, user_message, bot_name, raw_message)
            conv_histories[channel_id].append((bot.user.id, bot_name, response_without_context))
            if response_without_context:
                save_conv_history(conv_history)
                await raw_message.channel.send(
                    response_without_context,
                    reference = raw_message.to_reference(),  # Add this line to create a reply
                )
                return
            
    if f'<@{bot.user.id}>' in raw_message.content or is_reply_to_bot:
        # Get or create the conversation history for the current channel. This must go first!
        conv_history = conv_histories.setdefault(channel.id, deque(maxlen=50))

        # Split the message content and check if there is content after the bot mention
        update_message =  replace_mentions_with_usernames(raw_message.content, conv_history)
        if len(update_message) > 1:
            user_message = update_message + ".\n"  # Remove the bot mention
        else:
            return

        conv_histories[channel_id].append((raw_message.author.id, raw_message.author.name, update_message))
        conversation = shorten_conversation_history(conv_history)
        prompt = f"{personality_prompt}\n\n{conversation}"
        response = await generate_response(prompt, bot_name, raw_message, user_message, conversation)
        response_without_context = await get_response_without_context(response, user_message, bot_name, raw_message)
        response_without_context = replace_mentions_with_ids(response_without_context, conv_history)

         # Add this line to print the prompt
        logging.info(f"Prompt for on_message: {prompt}") 

        conv_history.append((bot.user.id, bot_name, response_without_context))
        save_conv_history(conv_history)
        await raw_message.channel.send(response_without_context)

        emoji_chance = random.random()
        if emoji_chance < 0.2:  # 20% chance to generate an emoji
            emoji = await generate_emoji(user_message, bot_name, raw_message, conversation)
            if emoji:
                try:
                    await raw_message.add_reaction(emoji)
                except HTTPException as e:
                    if e.code == 10014:  # Unknown Emoji
                        logging.info("Failed to add emoji reaction:", exc_info=e)
                    else:
                        raise
                except Exception as e:
                    logging.info("Failed to add emoji reaction:", exc_info=e)

    else:
        return None


#------------------------------------
#CLI
#------------------------------------
conv_history = []

def command_line_interface():
    while True:
        cmd = input("Type 'reset' to reset the bot, or 'quit' to quit: ").lower()
        if cmd == 'reset':
            conv_history.clear()
            logging.info("bot has been reset.")
        elif cmd == 'quit':
            logging.info("Shutting down the bot...")
            sys.exit(0)

cli_thread = threading.Thread(target=command_line_interface)
cli_thread.start()


bot.run(DISCORD_bot_TOKEN)



