import os
import random

from dotenv import load_dotenv
import psycopg2
import streamlit as st
import plotly.express as px

load_dotenv('variables.env')


st.set_page_config(
    page_title="EnglishCard - Изучение английского",
    page_icon="📚",
    layout="wide"
)


def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("HOST"),
        database=os.getenv("DATABASE"),
        user=os.getenv("USER"),
        password=os.getenv("PASSWORD"),
        port=os.getenv("PORT")
    )
    return conn


def init_database():
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS common_words (
                id SERIAL PRIMARY KEY,
                russian_word VARCHAR(100) NOT NULL,
                english_word VARCHAR(100) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (russian_word, english_word)
            );

            CREATE TABLE IF NOT EXISTS user_words (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                russian_word VARCHAR(100) NOT NULL,
                english_word VARCHAR(100) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, russian_word, english_word)
            );

            CREATE TABLE IF NOT EXISTS learning_stats (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                word_id INTEGER NOT NULL,
                word_type VARCHAR(8) NOT NULL CHECK (word_type IN ('common', 'personal')),
                correct_answers INTEGER NOT NULL DEFAULT 0,
                total_attempts INTEGER NOT NULL DEFAULT 0,
                last_reviewed TIMESTAMP NOT NULL DEFAULT NOW()
            );
        ''')

        # Заполнение common_words начальными словами (10 слов)
        cur.execute('''
            INSERT INTO common_words (russian_word, english_word)
            VALUES
                ('Яблоко', 'Apple'),
                ('Книга', 'Book'),
                ('Машина', 'Car'),
                ('Собака', 'Dog'),
                ('Слон', 'Elephant'),
                ('Цветок', 'Flower'),
                ('Солнце', 'Sun'),
                ('Дом', 'House'),
                ('Время', 'Time'),
                ('Вода', 'Water')
            ON CONFLICT (russian_word, english_word) DO NOTHING;
        ''')

        conn.commit()

    conn.close()


def login_user(username):
    stripped_username = username.strip()

    if not stripped_username:
        return None

    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT id
            FROM users
            WHERE username = %s;
        ''', (stripped_username,))

        result = cur.fetchone()

        if result:
            user_id = result[0]
        else:
            cur.execute('''
                INSERT INTO users (username, created_at)
                VALUES (%s, NOW())
                RETURNING id;
            ''', (stripped_username,))

            user_id = cur.fetchone()[0]

        conn.commit()

    conn.close()

    return user_id


def get_user_words(user_id):
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT id, russian_word, english_word, 'personal' as word_type
            FROM user_words
            WHERE user_id = %s
            UNION
            SELECT id, russian_word, english_word, 'common' as word_type
            FROM common_words;
        ''', (user_id,))
        words = cur.fetchall()

        result = []

        for word in words:
            result.append(
                {
                    'id': word[0],
                    'russian_word': word[1],
                    'english_word': word[2],
                    'word_type': word[3]
                }
            )

    conn.close()

    return result


def add_personal_word(user_id, russian_word, english_word):
    if not russian_word.strip() or not english_word.strip():
        return False

    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT id
            FROM user_words
            WHERE user_id = %s
            AND LOWER(russian_word) = LOWER(%s)
            AND LOWER(english_word) = LOWER(%s);
        ''', (user_id, russian_word.strip(), english_word.strip()))

        result = cur.fetchone()

        if result:
            success = False
        else:
            cur.execute('''
                INSERT INTO user_words (user_id, russian_word, english_word)
                VALUES (%s, %s, %s);
            ''', (user_id, russian_word.strip(), english_word.strip()))
            conn.commit()
            success = True

        conn.close()

        return success


def delete_personal_word(user_id, word_id):
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT id
            FROM user_words
            WHERE user_id = %s
            AND id = %s;
        ''', (user_id, word_id))

        result = cur.fetchone()

        if not result:
            success = False
        else:
            cur.execute('''
                DELETE FROM user_words
                WHERE user_id = %s
                AND id = %s;
            ''', (user_id, word_id))
            conn.commit()
            success = True

        conn.close()

        return success


def update_stats(user_id, word_id, word_type, is_correct):
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT id
            FROM learning_stats
            WHERE user_id = %s
            AND word_id = %s
            AND word_type = %s;
        ''', (user_id, word_id, word_type))

        result = cur.fetchone()

        if not result:
            cur.execute('''
                INSERT INTO learning_stats (user_id, word_id, word_type, correct_answers, total_attempts)
                VALUES (%s, %s, %s, %s, 1);
            ''', (user_id, word_id, word_type, 1 if is_correct else 0))

            conn.commit()
        else:
            cur.execute('''
                UPDATE learning_stats
                SET 
                    correct_answers = correct_answers + %s,
                    total_attempts = total_attempts + 1,
                    last_reviewed = NOW()
                WHERE user_id = %s
                AND word_id = %s
                AND word_type = %s;
            ''', (1 if is_correct else 0, user_id, word_id, word_type))

            conn.commit()

        conn.close()


def get_statistics(user_id):
    conn = get_db_connection()

    with conn.cursor() as cur:
        cur.execute('''
            SELECT 
                COALESCE(SUM(correct_answers), 0),
                COALESCE(SUM(total_attempts), 0)
            FROM learning_stats
            WHERE user_id = %s;
        ''', (user_id,))

        result = cur.fetchone()

        total_correct = result[0]
        total_attempts = result[1]

        cur.execute('''
            SELECT COUNT(*)
            FROM common_words
        ''')

        common_words_count = cur.fetchone()[0]

        cur.execute('''
            SELECT COUNT(*)
            FROM user_words
            WHERE user_id = %s;
        ''', (user_id,))

        personal_words_count = cur.fetchone()[0]

        accuracy = 0
        if total_attempts > 0:
            accuracy = round((total_correct / total_attempts) * 100, 2)

    conn.close()

    return {
        "common_words": common_words_count,
        "personal_words": personal_words_count,
        "total_words": common_words_count + personal_words_count,
        "accuracy": accuracy,
        "total_attempts": total_attempts,
        "total_correct": total_correct
    }


def generate_options(correct_word, all_words):
    options = [correct_word]

    other_words = [word['english_word'] for word in all_words if word['english_word'] != correct_word]

    if len(other_words) < 3:
        placeholders = [
            "август", "автор", "азбука", "академия", "алфавит", "альбом", "банан", "банка", "башня", "берег",
            "билет", "блюдо", "бумага", "вагон", "ведро", "ветер", "вечер", "вишня", "вода", "воздух",
            "вопрос", "время", "город", "гриб", "груша", "дерево", "деньги", "дождь", "дорога", "доска",
        ]

        for word in placeholders:
            if word not in options:
                options.append(word)
                if len(options) == 4:
                    break
    else:
        random_words = random.sample(other_words, 3)
        options.extend(random_words)

    random.shuffle(options)

    return options


def render_sidebar():
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2888/2888407.png", width=100)
        st.title("EnglishCard")

        if 'user_id' not in st.session_state or st.session_state.user_id is None:
            st.subheader("👤 Вход в систему")
            username = st.text_input("Введите ваше имя:", placeholder="Ваше имя...")

            if st.button("🚀 Начать обучение", use_container_width=True):
                if username:
                    user_id = login_user(username)
                    if user_id:
                        st.session_state.user_id = user_id
                        st.session_state.username = username.strip()
                        st.session_state.show_next = False
                        st.session_state.studied_words = []
                        st.success(f"✅ Добро пожаловать, {username}!")
                        st.rerun()
                else:
                    st.warning("⚠️ Пожалуйста, введите имя!")
        else:
            st.success(f"👋 Привет, {st.session_state.username}!")
            st.divider()

            stats = get_statistics(st.session_state.user_id)
            if stats:
                st.metric("📚 Всего слов", stats['total_words'])
                st.metric("🎯 Точность", f"{stats['accuracy']}%")

            st.divider()

            if st.button("🚪 Выйти", use_container_width=True):
                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state.show_next = False
                st.session_state.studied_words = []
                st.rerun()


def render_study_tab(words):
    st.header("📖 Изучаем слова")

    if not words:
        st.info("ℹ️ В словаре пока нет слов. Добавьте слова во вкладке '➕ Добавить слово'")
        return

    if 'show_next' not in st.session_state:
        st.session_state.show_next = False

    if 'current_word' not in st.session_state or st.session_state.get('words_changed', True):
        if words:
            st.session_state.current_word = random.choice(words)
            st.session_state.options = generate_options(st.session_state.current_word['english_word'], words)
            st.session_state.words_changed = False

    current_word = st.session_state.current_word

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"Слово: {current_word['russian_word']}")
    with col2:
        result_placeholder = st.empty()

    st.subheader("Как будет по-английски?")

    options = st.session_state.options
    correct_word = current_word['english_word']

    st.subheader("Выберите перевод:")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(label=options[0], key=1, use_container_width=True, disabled=st.session_state.show_next):
            if options[0] == correct_word:
                result_placeholder.success("✅ Правильно, вы молодец!")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], True)
                st.session_state.show_next = True
            else:
                result_placeholder.error(f"❌ Неправильно. Правильный ответ: {correct_word}")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], False)

    with col2:
        if st.button(label=options[1], key=2, use_container_width=True, disabled=st.session_state.show_next):
            if options[1] == correct_word:
                result_placeholder.success("✅ Правильно, вы молодец!")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], True)
                st.session_state.show_next = True
            else:
                result_placeholder.error(f"❌ Неправильно. Правильный ответ: {correct_word}")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], False)

    with col3:
        if st.button(label=options[2], key=3, use_container_width=True, disabled=st.session_state.show_next):
            if options[2] == correct_word:
                result_placeholder.success("✅ Правильно, вы молодец!")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], True)
                st.session_state.show_next = True
            else:
                result_placeholder.error(f"❌ Неправильно. Правильный ответ: {correct_word}")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], False)

    with col4:
        if st.button(label=options[3], key=4, use_container_width=True, disabled=st.session_state.show_next):
            if options[3] == correct_word:
                result_placeholder.success("✅ Правильно, вы молодец!")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], True)
                st.session_state.show_next = True
            else:
                result_placeholder.error(f"❌ Неправильно. Правильный ответ: {correct_word}")
                update_stats(st.session_state.user_id, current_word['id'], current_word['word_type'], False)

    if st.session_state.show_next:
        if st.button(label="➡️ Следующее слово", use_container_width=True):
            st.session_state.show_next = False
            st.session_state.words_changed = True
            result_placeholder.empty()
            st.rerun()


def render_add_word_tab():
    st.header("➕ Добавить слово")

    if st.session_state.user_id is None:
        st.warning("⚠️ Пожалуйста, авторизуйтесь для добавления слов")
        return

    with st.form("add_word_form", clear_on_submit=True):
        russian_word = st.text_input("Введите слово на русском:", placeholder="Например: Компьютер")
        english_word = st.text_input("Введите перевод на английский:", placeholder="Например: Computer")

        submit = st.form_submit_button("📝 Добавить слово", use_container_width=True)

        if submit:
            if not russian_word.strip() or not english_word.strip():
                st.error("❌ Пожалуйста, заполните оба поля!")
            else:
                success = add_personal_word(st.session_state.user_id, russian_word, english_word)
                if success:
                    st.success(f"✅ Слово '{russian_word} - {english_word}' успешно добавлено в словарь!")
                    st.session_state.words_changed = True
                else:
                    st.error(f"❌ Слово '{russian_word} - {english_word}' уже есть в вашем словаре!")


def render_delete_word_tab(words):
    st.header("🗑️ Удалить слово")

    if st.session_state.user_id is None:
        st.warning("⚠️ Пожалуйста, авторизуйтесь для удаления слов")
        return

    personal_words = [word for word in words if word['word_type'] == 'personal']

    if not personal_words:
        st.info("ℹ️ У вас пока нет персональных слов для удаления")
        return

    with st.form("delete_word_form"):
        word_options = {f"{word['russian_word']} - {word['english_word']}": word['id'] for word in personal_words}
        selected_word_display = st.selectbox(
            "Выберите слово для удаления:",
            options=list(word_options.keys())
        )

        submit = st.form_submit_button("🗑️ Удалить слово", use_container_width=True)

        if submit:
            word_id = word_options[selected_word_display]
            success = delete_personal_word(st.session_state.user_id, word_id)
            if success:
                st.success(f"✅ Слово '{selected_word_display}' успешно удалено!")
                st.session_state.words_changed = True
                st.rerun()
            else:
                st.error("❌ Произошла ошибка при удалении слова")


def render_statistics_tab(user_id):
    st.header("📊 Статистика")

    stats = get_statistics(user_id)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📚 Изучено слов", stats['total_words'])
    with col2:
        st.metric("📝 Всего попыток", stats['total_attempts'])
    with col3:
        st.metric("🎯 Точность", f"{stats['accuracy']}%")

    if stats['total_attempts'] > 0:
        st.divider()

        data = {
            'Категория': ['Правильные', 'Неправильные'],
            'Количество': [stats['total_correct'], stats['total_attempts'] - stats['total_correct']]
        }

        fig = px.pie(
            data,
            values='Количество',
            names='Категория',
            color='Категория',
            color_discrete_map={'Правильные': '#00cc66', 'Неправильные': '#ff6666'}
        )

        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ Нет данных для отображения статистики. Начните изучение слов!")


def main():
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.show_next = False
        st.session_state.studied_words = []
        st.session_state.words_changed = True

    init_database()

    st.title("📚 EnglishCard - Изучай английский с удовольствием!")

    render_sidebar()

    if st.session_state.user_id:
        words = get_user_words(st.session_state.user_id)

        tab1, tab2, tab3, tab4 = st.tabs(["📖 Изучение", "➕ Добавить слово", "🗑️ Удалить слово", "📊 Статистика"])

        with tab1:
            render_study_tab(words)
        with tab2:
            render_add_word_tab()
        with tab3:
            render_delete_word_tab(words)
        with tab4:
            render_statistics_tab(st.session_state.user_id)
    else:
        st.markdown("""
        ### 👋 Привет! Давай попрактикуемся в английском языке.
        Тренировки можешь проходить в удобном для себя темпе, для этого воспользуйся инструментом "📖 Изучение".

        Также у тебя есть возможность использовать тренажёр, как конструктор, 
        и собирать свою собственную базу для обучения. Для этого воспользуйся инструментами:

        - ➕ **Добавить слово**
        - 🗑️ **Удалить слово**

        Если ты захочешь посмотреть свои результаты, используй инструмент "📊 Статистика"

        🍀 Удачи в изучении!
        """)
        st.divider()


if __name__ == "__main__":
    main()