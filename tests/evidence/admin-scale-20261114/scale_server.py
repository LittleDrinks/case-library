import os
from app.core.config import Settings
from app.core.database import connect, initialize
from app.main import create_app
from app.modules.auth.seed import seed_demo_users
from app.modules.tags.seed import seed_demo_tags

# 该入口只初始化隔离的合成验证数据库。
settings = Settings(app_environment='test', mongo_uri=os.environ['MONGODB_URI'], mongo_database='case_library_admin_scale_20261114', session_cookie_secure=False)
client, database = connect(settings)
assert settings.mongo_database == 'case_library_admin_scale_20261114'
client.drop_database(settings.mongo_database)
initialize(database)
seed_demo_users(database)
seed_demo_tags(database)
stamp = '2026-11-14T00:00:00+00:00'
database.cases.insert_many([dict(id=f'scale-case-{i:05}', title=f'教学案例 {i:05}' + (' [专题]' if i % 100 == 0 else ''), author='合成教师', ownerId='u-teacher', workflowStatus='pending' if i < 10000 else 'published', publicationStatus='private' if i < 10000 else ('hidden' if i % 2 else 'public'), updatedAt=stamp, publishedAt=stamp, document={'type':'doc','content':[]}) for i in range(20000)])
database.material_candidates.insert_many([dict(id=f'scale-material-{i:05}', filename=f'课堂观察 {i:05}' + (' [专题]' if i % 100 == 0 else '') + '.txt', sha256=f'synthetic-{i:05}', mediaType='text/plain', size=1024, accessLevel='campus', status='candidate', createdBy='u-admin',createdAt=stamp) for i in range(10000)])
database.skills.insert_many([dict(id=f'scale-skill-{i:04}', name=f'教学技能 {i:04}' + (' [专题]' if i % 100 == 0 else ''), description='合成验证样例', createdAt=stamp, latestVersionId=f'scale-version-{i * 10 + 9:05}', **({'publishedVersionId':f'scale-version-{i * 10 + 9:05}'} if i % 2 == 0 else {})) for i in range(1000)])
database.skill_versions.insert_many([dict(id=f'scale-version-{i:05}', skillId=f'scale-skill-{i // 10:04}', version=i % 10 + 1, packageSha256='synthetic-package', size=1024, fileCount=1, name=f'教学技能 {i // 10:04}', description='合成验证样例', createdAt=stamp, body='not returned', files=['not returned']) for i in range(10000)])
app = create_app(database=database, settings=settings)
print('Isolated scale database seeded: 10000 rows per review/published/material/skill-version queue.', flush=True)
