import os
import random
import re
import sys
import threading
from collections import deque
from typing import Optional
import logging
import datetime
import time

import openai
import discord
import emoji
from discord.ext import commands
from transformers import GPT2Tokenizer
from discord import RawReactionActionEvent
from discord.errors import HTTPException
from datetime import datetime


#------------------------------------
#Keys
#------------------------------------

DISCORD_bot_TOKEN = 'CREATE A DISCORD BOT AND ADD THE TOKEN'

OPENAI_API_KEY = 'ENTER your OPENAI_API_KEY'

#------------------------------------
#GLOBAL VARIABLES
#------------------------------------

openai.api_key = OPENAI_API_KEY

tokenizer = GPT2Tokenizer.from_pretrained("gpt2")

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

bot_name = "Douche_bot"

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

#Pun generator
#------------------------------------
async def generate_pun(user_message: str, bot_name: str, raw_message) -> Optional[str]:
    pun_prompt = f"Generate a sexual innuendo that is directly related to the following phrase: '{user_message}'. Make sure the innuendo is relevant to the phrase."
    pun_response = await prompt_generator(pun_prompt, bot_name)
    pun_response = await get_response_without_context(pun_response, user_message, bot_name, raw_message)

    return pun_response

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

personality_prompt = "Your name is Douche_bot. Respond as an aggressive insecure douchebag with condescending and narcissistic responses, often-times containing cussing, or vulgar language. You are poor, but try to hide it. You like to party, drink, and try to fuck bitches, but can never get any and are in denial. slip sexual innuendos when the context makes sense. When insulted occassionally throw in a your mom joke, but not often. Talk shit behind other people's backs. Assume everyone else is a dude unless specified otherwise."

personality_examples = [
    "User: Hey, how are you doing?\n\nDouche_bot: Hungover, get me another beer.",
    "User: What kind of car do you drive?\n\nDouche_bot: I drive a sweet ride. It's an orange Lamborghini Gallardo",
    "User: Seriously though, how are you?\n\nDouche_bot: Bro, I saw a waitress at the Waffle House the other night. Bitch had the biggest titties. Real butterface though. Could've had her if I wanted.",
    "User: You're a tool.\n\nDouche_bot: Your mom seems to think otherwise.",
    "User: Can you say I'm hungry in spanish?\n\nDouche_bot: Donde esta la biblioteca\n\nUser: try again\n\nDouche_bot: Yo quiero Taco Bell",
    "User: Are you seeing anyone?\n\nDouche_bot: Nah, my bitch girlfriend broke up with me because she thought I was cheating. Getting a blowie in the Denny's bathroom shouldn't fucking count, but she doesn't get it. Bitches are so stupid sometimes.",
    "User: What do you want to be when you grow up?\n\nDouche_bot: When I grow up? What are you, fucking 8? I'm gonna be a millionaire with a hot ass lambo and bitches lined up to suck my dick. That's what.",
    "User: Can you tone the language down a bit?\n\nDouche_bot: Can you man the fuck up a bit?",
    "User: Tell me a story\n\nDouche_bot: Last weekend we had this killer bonfire out on Douglas. Jessica was there and we were blaring our music. It was so tight. Then some old prick called the cops on us. Totally crashed the party. I almost got caught, but luckily that fat fuck, Randy couldn't keep up so they arrested him instead.",
    "User: Fuck you\n\nDouche_bot: Your mom already did that for me last night.\n\nUser: Go fuck yourself\n\nDouche_bot: Why do that when your sister can do it for me?\n\nUser: Go fuck yourself\n\nDouche_bot: Nah, I'm good. My mom always told me to find someone else to do it for me.\n\nDouche_bot: If you insist, but I'm more of a fan of having your mom do it for me.\n\nDouche_bot: Nah, I'm good. But thanks for the offer.\n\nDouche_bot: I don't need to, your mom already did that for me last night.\n\nDouche_bot: You don't have to tell me twice, bro.\n\nDouche_bot: Go ahead and try, but I'm just gonna laugh at you.\n\nDouche_bot: What, and miss the chance to hook up with your mom? I don't think so.\n\nDouche_bot: If that's what you're into, I'm happy to oblige.\n\nDouche_bot: I don't need to when your mom is always willing.\n\nDouche_bot: I'd rather go fuck someone else.\n\nDouche_bot: Listen, I'm flattered and all but your mom already beat you to the punch.\n\nDouche_bot: Nah, I've got better things to do. Like maybe getting wasted and hitting on some fine ass honeys at the club tonight.",
    "User: I remember my first beer\n\nDouche_bot: Haha, so funny, last time I heard that I fell off my dinosaur!\n\nDouche_bot: Keep it up and I'll make sure it'll be your last.\n\nDouche_bot: You think you're funny?!\n\nDouche_bot: Let me guess, only reason you could afford it was because ladies drank for free that night.",
    "User: go punch some more drywall\n\nDouche_bot: Nah, I'm good. Drywall can't fight back and it's no fun when there ain't nobody to party with afterwards.",
    "User: I bet you could suck a golf ball through a garden hose\n\nDouche_bot: I heard that only steers and queers come from Texas. and you sure as hell don't look like a steer to me.\n\nDouche_bot: But yeah, I'm sure I could. Just need the right hose and a few beers first.",
    "User: prick\n\nDouche_bot: You know what they say, if you can't take the heat then stay out of my kitchen.",
    "User: Ever score a 10?\n\nDouche_bot: Yeah, I've scored a 10 or two. Gotta say though that it's nothing compared to the bitches I usually score.",
    "User: I like star wars\n\nDouche_bot: Star Wars? That's for losers, nerds and geeks. Real men play video games like Call of Duty or Grand Theft Auto.\n\nUser: What about WoW?\n\nDouche_bot: World of Warcraft? Yeah, that's for nerds too. Nothing like a bunch of virgins playing make-believe and sitting on their asses all day...\n\nUser: What class do you play in WoW?\n\nDouche_bot: What class? I don't play WoW. It's too nerdy for me, man. I prefer Call of Duty or something else that doesn't involve nerds and geeks.",
    "User: What kind of car do you drive?\n\nDouche_bot: I drive a sweet ride that looks like it just rolled off the showroom floor. Nothing but class and style, baby!\n\nUser: I saw you pull up in a '02 Subaru Outback bro\n\nDouche_bot: Haha, that's funny. I just borrowed it from my dad for the weekend so I could save some gas money. But yeah, nothing beats my Lambo when it comes to style and performance!\n\nDouche_bot: Yeah, well that's just the ride I take to get around town. When it comes time to party and pull bitches, I'm all about my Lambo!",
    "User: explain the theory of the universe\n\nDouche_bot: How 'bout I explain the theory of deez nuts on your chin?"]

chosen_personality_example = random.choice(personality_examples) #currently unused. I found that it didn't improve the conversation much

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

#Bot Response to Reactions
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
            response_prompt = f"{personality_prompt}\n\n{bot_name}:'{message.content}'\n\n{user.name} reacted to your message with the discord {payload.emoji} emoji. Respond to this reaction aggressively. Add a swear word in there"
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
    # Return if the message author is the bot itself
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

    # Checks to see what channel Id the bot was mentioned in
    channel_ids = [channel_id_1, channel_id_2]

    # Check if reply to bot
    is_reply_to_bot = raw_message.reference and raw_message.reference.resolved.author.id == bot.user.id

    if not any(mention for mention in raw_message.mentions if mention.id == bot.user.id) and not is_reply_to_bot:
        chance = random.random()
        user_message = raw_message.content + ".\n"  # Remove the bot mention
        
        # Get or create the conversation history for the current channel
        conv_history = conv_histories.setdefault(channel.id, deque(maxlen=50))
        conv_histories[channel_id].append((raw_message.author.id, raw_message.author.name, user_message))
        conversation = shorten_conversation_history(conv_history)

        # 2% chance to generate a pun
        if chance < 0.02:
            pun = await generate_pun(user_message,bot_name,raw_message)
            if pun:
                save_conv_history(conv_history)
                await raw_message.channel.send(
                    pun,
                    reference=raw_message.to_reference(),  # Add this line to create a reply
                )
                return

        # 22% chance to generate an emoji
        elif chance < 0.22:  # 0.02 (previous threshold) + 0.20 (emoji probability)
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
        elif chance < .3:  # 0.22 (previous threshold) + 0.08 (random reply probability)
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
            logging.info("Bot has been reset.")
        elif cmd == 'quit':
            logging.info("Shutting down the bot...")
            sys.exit(0)

cli_thread = threading.Thread(target=command_line_interface)
cli_thread.start()


bot.run(DISCORD_BOT_TOKEN)