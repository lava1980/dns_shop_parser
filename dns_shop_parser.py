import requests, os
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import time, bs4, sys, sqlite3, pprint
import smtplib, email
from email.mime.text import MIMEText
from email.header import Header
import settings



start_time = time.time()
options = webdriver.FirefoxOptions()
options.headless = False
driver = webdriver.Firefox()

url = 'https://www.dns-shop.ru/catalog/markdown/'
city_list = settings.city_list

def choose_city(town):
    driver.get(url)

    # Кликаем на выбор города
    try:
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//div[@class="header-top"]/div/ul/li/div/div')))
        time.sleep(1)
        driver.find_element_by_xpath('//div[@class="header-top"]/div/ul/li/div/div').click()

    except:
        driver.find_element_by_xpath('//div[@class="header-top"]/div/ul/li/div/div').click()
        #driver.find_element_by_link_text(town).click()

    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//div[@class="search-field"]/input')))
    search_field = driver.find_element_by_xpath('//div[@class="search-field"]/input')
    search_field.send_keys(town)  # В окне поиска вводим город

    # Кликаем на город
    gorod_list = driver.find_elements_by_xpath('//div/div/div/ul/li/a/span/mark/..')
    for gorod in gorod_list:
        if town == gorod.text:
            gorod.click()
        else:
            continue

    WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element(
        (By.XPATH, '//div[@class="navbar-menu"]/div/div/ul/li/div/div'), town))

    driver.current_window_handle
    soup = bs4.BeautifulSoup(driver.page_source, 'lxml')
    # Обновление инфы об общем числе товаров
    count_of_items = soup.find('div', class_='page-content-container').find('span').get_text().strip().replace(' ', '')
    count_of_items = int(count_of_items[:count_of_items.find('товар')])
    count_of_pages = (count_of_items - 20) // 20 if (count_of_items - 20) % 20 == 0 else (count_of_items - 20) // 20 + 1

    return count_of_pages





def data_to_base(page_url): # Получаем данные для базы с одной страницы
    driver.get(page_url)
    soup = bs4.BeautifulSoup(driver.page_source, 'lxml')
    # Обновление инфы об общем числе товаров
    count_of_items = soup.find('div', class_='page-content-container').find('span').get_text().strip().replace(' ', '')
    count_of_items = int(count_of_items[:count_of_items.find('товар')])
    count_of_pages = (count_of_items - 20) // 20 if (count_of_items - 20) % 20 == 0 else (count_of_items - 20) // 20 + 1

    list_of_blocks = soup.find_all('div', class_='product')
    data_to_base = []

    for block in list_of_blocks:
        name = block.find('div', class_='item-name').find('a').get_text()
        link = 'https://www.dns-shop.ru' + block.find('div', class_='item-name').find('a').get('href')

        curr_price = int(block.find('div', class_='price_g').find('span').get_text().replace(' ', ''))

        try:
            old_price = int(block.find('div', class_='markdown-price-old').get_text().replace(' ', ''))
            diff = old_price - curr_price
        except AttributeError:
            old_price = None
            diff = None

        id = link[41:-1]

        data_to_base.append(
            (id, name, link, old_price, curr_price, diff))

    return data_to_base, count_of_pages



def update_base(data, name_of_table):
    conn = sqlite3.connect("markdown_base.db")  # или :memory: чтобы сохранить в RAM
    cursor = conn.cursor()

    try:
        # Создание таблицы
        cursor.execute(f"""CREATE TABLE {name_of_table}
                              (id text PRIMARY KEY, name text, link text, old_price integer,
                               curr_price integer, diff integer)
                           """)

        # Вставляем данные в таблицу
        cursor.executemany(f"INSERT INTO {name_of_table} VALUES (?,?,?,?,?,?)", data)

    except sqlite3.OperationalError:
        pass


    cursor.execute(f"SELECT id, curr_price FROM {name_of_table}")

    id_list = cursor.fetchall()

    count_of_update = 0
    count_of_insert = 0

    markdown_list = []
    new_item_list = []

    for data_id in data:
        for table_data in id_list:
            if data_id[0] == table_data[0]: # сравнивается строка новых данных (data_id) с каждой строкой из таблицы
                if data_id[4] != table_data[1]:
                    cursor.execute(f"UPDATE {name_of_table} SET old_price=?, curr_price=?, diff=? WHERE id=?",
                                   (data_id[3], data_id[4], data_id[5], data_id[0]))
                    markdown_list.append(data_id)
                    count_of_update += 1
                    break
                else: break

        if data_id[0] != table_data[0]:
            cursor.execute(f"INSERT INTO {name_of_table} VALUES (?,?,?,?,?,?)", data_id)
            new_item_list.append(data_id)
            count_of_insert += 1

    print('Добавлено ' + str(count_of_insert) + '.\nОбновлено ' + str(count_of_update) + '.')
    #print(new_item_list)
    #print(markdown_list)

    # Сохраняем изменения
    conn.commit()
    conn.close()

    return new_item_list, markdown_list


def result_data_handler(result_data):
    message = ''
    for item in result_data:
        message = message + item[1] + '\n' + item[2] + '\n' + 'Старая цена: ' + str(item[3]) + '\n' + \
                  'Текущая цена: ' + str(item[4]) + '\n' + 'Разница: ' + str(item[5]) + '\n' + \
                  '--------------' + '\n'
    if 'None' in message:
        message = message.replace('None', '')
    return message



def send_mail(message):
    smtp_host = settings.email_data.get('smtp_host')
    login = settings.email_data.get('login')
    password = settings.email_data.get('password')
    recipients_emails = settings.email_data.get('recipients_emails')

    msg = MIMEText(message, 'plain', 'utf-8')
    msg['Subject'] = Header('Обновление данных на dns-shop.ru', 'utf-8')
    msg['From'] = settings.email_data.get('from')
    msg['To'] = recipients_emails

    s = smtplib.SMTP(smtp_host, 587, timeout=10)
    # s.set_debuglevel(1)
    try:
        s.starttls()
        s.login(login, password)
        s.sendmail(msg['From'], recipients_emails, msg.as_string())
    finally:
        print(msg)
        s.quit()



def get_city_data(city):
    count_of_pages = choose_city(city)

    new_item = []
    markdown = []

    for i in range(count_of_pages + 1):

        if i == 0:
            page_url = url
        else:
            page_url = url + '?offset=' + str(i * 20)

        data, count_of_pages = data_to_base(page_url) # получаем данные для базы
        new_item_list, markdown_list = update_base(data, city) # запись в базу
        new_item = new_item + new_item_list
        markdown = markdown + markdown_list

    new_item_message = result_data_handler(new_item)
    markdown_message = result_data_handler(markdown)

    whole_message = '***** НОВЫЕ ТОВАРЫ ПО ГОРОДУ ' + city + ' *****' + '\n\n' + new_item_message + '\n\n' + \
                    '***** УЦЕНЁННЫЕ ТОВАРЫ ПО ГОРОДУ ' + city + ' *****' + '\n\n' + markdown_message

    return whole_message



def main():
    for city in city_list:
        mess = get_city_data(city)
        if len(mess) > 150:
            send_mail(mess)
    driver.close()
    print("--- На выполение скрипта ушло: %s минут ---" % int(((time.time() - start_time))/60))



if __name__ == '__main__':
    main()


